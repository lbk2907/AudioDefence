package com.audiodefence;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * Unpacking the game's data from the APK, only the files that changed.
 *
 * <p>The build lists what the phone unpacks - every file under game/, the language files under localization/
 * and VERSION - in the APK's assets as data-manifest.txt, each with its CRC-32 and size (app/build.gradle,
 * writeDataManifest).  The phone keeps the list of what it last unpacked beside the data, as
 * .data-&lt;DATA_VERSION&gt;.manifest, and on every start compares the two: a file that is new, has changed, or is
 * missing or the wrong size on the phone is copied; a file the game no longer has is deleted, under game/ only;
 * and the new list is saved once every copy has succeeded.  Anything else in the folder - the player's settings
 * and saves, a language file of their own - is in neither list and is never touched.
 *
 * <p>No saved list, or one that cannot be read, and the whole of game/ is unpacked again: a first install, a phone
 * coming from the app that kept only a marker, and a raised DATA_VERSION all take that path.
 *
 * <p>Nothing here is Android's, so the whole of it can be checked on a computer: MainActivity hands it the APK's
 * assets as a {@link Source} and speaks for it through a {@link Listener}.
 */
final class DataSync {
    /** The build's list, at the root of the APK's assets. */
    static final String ASSET_MANIFEST = "data-manifest.txt";
    /** The first line of a list; the build writes the same (app/build.gradle). */
    static final String MAGIC = "audiodefence-data-manifest 1";
    /** Every file of the app's own in the data folder starts with this: the old markers, the saved list. */
    static final String PREFIX = ".data-";

    // How much copying the player is told about.  Judgement, not measured on a phone: a few files go by before
    // the game speaks, so they are copied in silence; more than that is announced, and a lot gets percentages.
    static final int QUIET_FILES = 40;
    static final long QUIET_BYTES = 8L << 20;
    static final int PROGRESS_FILES = 400;
    static final long PROGRESS_BYTES = 40L << 20;
    /** What opening and closing one file is worth in bytes, for the percentages: thousands of small sounds
     *  take longer than their size says. */
    static final long FILE_COST = 32L << 10;

    private DataSync() {
    }

    /** Where the files come from: the APK's assets on the phone, a stand-in in a test. */
    interface Source {
        InputStream open(String path) throws IOException;
    }

    /** What the player hears.  Called only when there is something to copy or delete. */
    interface Listener {
        void starting(Plan plan);

        /** 20, 40, 60 and 80, when the plan has percentages. */
        void progress(int percent);

        void finished(Plan plan);
    }

    /** One file of a list: its CRC-32, as eight lower-case hex digits, and its size. */
    static final class Entry {
        final String crc;
        final long size;

        Entry(String crc, long size) {
            this.crc = crc;
            this.size = size;
        }

        @Override
        public boolean equals(Object o) {
            return o instanceof Entry && ((Entry) o).crc.equals(crc) && ((Entry) o).size == size;
        }

        @Override
        public int hashCode() {
            return crc.hashCode() * 31 + Long.hashCode(size);
        }
    }

    /** The size of a file in the data folder, or -1 when it is not there. */
    interface Disk {
        long size(String path);
    }

    /** What one start has to do. */
    static final class Plan {
        /** No usable saved list: game/ is emptied and everything is copied. */
        final boolean full;
        /** To copy, in order. */
        final List<String> copy;
        /** To delete: in the saved list, not in the APK's, and under game/. */
        final List<String> delete;
        final long copyBytes;

        Plan(boolean full, Map<String, Entry> wanted, List<String> copy, List<String> delete) {
            this.full = full;
            this.copy = copy;
            this.delete = delete;
            long b = 0;
            for (String p : copy) {
                b += wanted.get(p).size;
            }
            this.copyBytes = b;
        }

        boolean nothingToDo() {
            return !full && copy.isEmpty() && delete.isEmpty();
        }

        /** Worth a line before it and "The game is ready." after. */
        boolean announce() {
            return full || copy.size() > QUIET_FILES || copyBytes > QUIET_BYTES;
        }

        /** Worth saying how far it has got. */
        boolean percentages() {
            return full || copy.size() > PROGRESS_FILES || copyBytes > PROGRESS_BYTES;
        }
    }

    // ------------------------------------------------------------------------------------------- lists
    /** A list read, or null when it is not one: no first line, a line that does not parse, a path that climbs
     *  out of the folder, a path twice, or no closing count to say it was written to the end. */
    static Map<String, Entry> parse(InputStream in) {
        try (BufferedReader r = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            if (!MAGIC.equals(r.readLine())) {
                return null;
            }
            Map<String, Entry> m = new TreeMap<>();
            String line;
            while ((line = r.readLine()) != null) {
                if (line.startsWith("end\t")) {
                    int n = Integer.parseInt(line.substring(4));
                    return n == m.size() && r.readLine() == null ? m : null;
                }
                String[] f = line.split("\t", 3);
                if (f.length != 3 || !isCrc(f[0]) || !isSafePath(f[2])) {
                    return null;
                }
                long size = Long.parseLong(f[1]);
                if (size < 0 || m.put(f[2], new Entry(f[0], size)) != null) {
                    return null;
                }
            }
            return null;                                        // cut short
        } catch (IOException | RuntimeException e) {
            return null;
        }
    }

    /** The saved list, or null when there is none or it cannot be read. */
    static Map<String, Entry> read(File f) {
        if (!f.isFile()) {
            return null;
        }
        try (InputStream in = new FileInputStream(f)) {
            return parse(in);
        } catch (IOException e) {
            return null;
        }
    }

    static String format(Map<String, Entry> m) {
        StringBuilder sb = new StringBuilder(MAGIC).append('\n');
        for (Map.Entry<String, Entry> e : new TreeMap<>(m).entrySet()) {
            sb.append(e.getValue().crc).append('\t').append(e.getValue().size).append('\t').append(e.getKey())
                    .append('\n');
        }
        return sb.append("end\t").append(m.size()).append('\n').toString();
    }

    /** Writes a list whole or not at all: to a file beside it, then moved over it. */
    static void write(File f, Map<String, Entry> m) throws IOException {
        File parent = f.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IOException("cannot create " + parent);
        }
        File tmp = new File(parent, f.getName() + ".tmp");
        try (FileOutputStream out = new FileOutputStream(tmp)) {
            out.write(format(m).getBytes(StandardCharsets.UTF_8));
            out.getFD().sync();
        }
        try {
            Files.move(tmp.toPath(), f.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(tmp.toPath(), f.toPath(), StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private static boolean isCrc(String s) {
        if (s.length() != 8) {
            return false;
        }
        for (int i = 0; i < 8; i++) {
            char c = s.charAt(i);
            if (!(c >= '0' && c <= '9' || c >= 'a' && c <= 'f')) {
                return false;
            }
        }
        return true;
    }

    /** A path relative to the data folder that stays inside it, and is not one of the app's own files. */
    static boolean isSafePath(String p) {
        if (p.isEmpty() || p.startsWith("/") || p.indexOf('\\') >= 0 || p.indexOf('\0') >= 0
                || p.startsWith(PREFIX)) {
            return false;
        }
        for (String part : p.split("/", -1)) {
            if (part.isEmpty() || part.equals(".") || part.equals("..")) {
                return false;
            }
        }
        return true;
    }

    private static boolean underGame(String p) {
        return p.startsWith("game/");
    }

    // -------------------------------------------------------------------------------------------- plan
    /** What to do, given the APK's list, the saved one (null when there is none) and what is on the phone. */
    static Plan plan(Map<String, Entry> wanted, Map<String, Entry> saved, Disk disk) {
        List<String> copy = new ArrayList<>();
        List<String> delete = new ArrayList<>();
        if (saved == null) {
            copy.addAll(new TreeMap<>(wanted).keySet());
            return new Plan(true, wanted, copy, delete);
        }
        for (Map.Entry<String, Entry> e : new TreeMap<>(wanted).entrySet()) {
            Entry was = saved.get(e.getKey());
            // a file the saved list has right is still checked for being there at its size: one cut short or
            // gone is put back, which costs a look at each file and no reading
            if (!e.getValue().equals(was) || disk.size(e.getKey()) != e.getValue().size) {
                copy.add(e.getKey());
            }
        }
        for (String p : new TreeMap<>(saved).keySet()) {
            if (!wanted.containsKey(p) && underGame(p)) {
                delete.add(p);
            }
        }
        return new Plan(false, wanted, copy, delete);
    }

    // -------------------------------------------------------------------------------------------- sync
    /** The saved list's file: its name carries DATA_VERSION, so raising that leaves no list to find. */
    static File savedManifest(File home, int dataVersion) {
        return new File(home, PREFIX + dataVersion + ".manifest");
    }

    /**
     * Brings the data folder level with the APK.  Returns whether anything was copied or deleted.  Throws when
     * the APK's list cannot be read or a file cannot be copied: the saved list then still lists only what is in
     * place, so the next start does the rest.
     */
    static boolean sync(File home, int dataVersion, Source src, Listener listener) throws IOException {
        Map<String, Entry> wanted;
        try (InputStream in = src.open(ASSET_MANIFEST)) {
            wanted = parse(in);
        }
        if (wanted == null) {
            throw new IOException("the APK's " + ASSET_MANIFEST + " cannot be read");
        }
        File savedFile = savedManifest(home, dataVersion);
        removeOldFiles(home, savedFile.getName());              // the old markers, and lists of another DATA_VERSION
        Map<String, Entry> saved = read(savedFile);
        Plan plan = plan(wanted, saved, path -> {
            File f = new File(home, path);
            return f.isFile() ? f.length() : -1;
        });
        if (plan.nothingToDo()) {
            return false;
        }
        listener.starting(plan);

        Set<String> kept = new HashSet<>();                     // deletions that failed stay listed, to try again
        if (plan.full) {
            //noinspection ResultOfMethodCallIgnored
            savedFile.delete();
            deleteRecursive(new File(home, "game"));
        } else {
            if (!plan.copy.isEmpty()) {
                // Until the copies are done, the saved list holds only the files known to be in place: what is
                // about to be copied is left out, so an unpack cut off half way copies it again next time, even
                // when the APK by then has an older version of it back.
                Map<String, Entry> interim = new TreeMap<>(saved);
                interim.keySet().removeAll(plan.copy);
                write(savedFile, interim);
            }
            File gameDir = new File(home, "game");
            for (String p : plan.delete) {
                File f = new File(home, p);
                if (f.isFile() && !f.delete()) {
                    kept.add(p);
                    continue;
                }
                pruneEmptyFolders(f.getParentFile(), gameDir);
            }
        }

        long total = 0;
        for (String p : plan.copy) {
            total += wanted.get(p).size + FILE_COST;
        }
        Progress progress = new Progress(plan.percentages() ? listener : null, total);
        byte[] buf = new byte[65536];
        for (String p : plan.copy) {
            copy(src, p, wanted.get(p).size, new File(home, p), buf, progress);
            progress.add(FILE_COST);
        }

        Map<String, Entry> now = new TreeMap<>(wanted);
        for (String p : kept) {
            now.put(p, saved.get(p));
        }
        write(savedFile, now);
        listener.finished(plan);
        return true;
    }

    private static final class Progress {
        private final Listener listener;
        private final long total;
        private long done;
        private int said;

        Progress(Listener listener, long total) {
            this.listener = listener;
            this.total = total;
        }

        void add(long n) {
            done += n;
            if (listener == null || total <= 0) {
                return;
            }
            int step = (int) (done * 5 / total);                // fifths
            while (said < step && said < 4) {
                said++;
                listener.progress(said * 20);
            }
        }
    }

    private static void copy(Source src, String path, long size, File target, byte[] buf, Progress progress)
            throws IOException {
        File parent = target.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IOException("cannot create " + parent);
        }
        long n = 0;
        try (InputStream in = src.open(path); OutputStream out = new FileOutputStream(target)) {
            int k;
            while ((k = in.read(buf)) > 0) {
                out.write(buf, 0, k);
                n += k;
                progress.add(k);
            }
        }
        if (n != size) {
            throw new IOException(path + " is " + n + " bytes in the APK; its list says " + size);
        }
    }

    /** The old markers (.data-&lt;version&gt;-&lt;installed&gt;), a list left half written, and a list of another
     *  DATA_VERSION. */
    static void removeOldFiles(File home, String keep) {
        File[] old = home.listFiles((dir, name) -> name.startsWith(PREFIX) && !name.equals(keep));
        if (old != null) {
            for (File f : old) {
                if (f.isFile()) {
                    //noinspection ResultOfMethodCallIgnored
                    f.delete();
                }
            }
        }
    }

    /** Folders left empty by a deletion, up to game/ itself. */
    private static void pruneEmptyFolders(File dir, File stop) {
        while (dir != null && !dir.equals(stop)) {
            String[] left = dir.list();
            if (left == null || left.length > 0 || !dir.delete()) {
                return;
            }
            dir = dir.getParentFile();
        }
    }

    static void deleteRecursive(File f) {
        File[] kids = f.listFiles();
        if (kids != null) {
            for (File k : kids) {
                deleteRecursive(k);
            }
        }
        //noinspection ResultOfMethodCallIgnored
        f.delete();
    }
}
