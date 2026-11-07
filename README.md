# JAS CD Recovery

This repository contains some programs for extracting audio from TASCAM 788 data backup CDs which are stored in a proprietary format that you need the TASCAM equipment to read and extract. Since I was unable to get the CD-RW device working in order to extract the WAV files themselves from the CDs I opted to work with Claude (Opus 5) to reverse-engineer a program for extracting the data from a dump of the raw CD data.

## rip.sh

Put a backup disc in the drive, find its device with `diskutil list`, and run:

```
mkdir -p logs
./rip.sh song_name /dev/disk4 2>&1 | tee logs/song_name.log
```

For each disc it:

1. Images the whole disc with ddrescue, reading the uncached `/dev/rdisk4`
   in 2352-byte sectors, to `song_name.raw`, with ddrescue's mapfile in
   `song_name.map`.
2. Reads the disc's 2048-byte user data with cdrdao to `song_name.bin`.
3. Checks every sector of the `.raw` with `verify_raw.py`: the sync
   pattern, the sector's own address, its EDC checksum, and its user data
   against the `.bin`. This decides whether the disc passes.
4. Extracts all the audio on the disc from the `.bin` as one mono WAV,
   `song_name.wav`, with `extract_audio.py`, which works out whether the disc
   holds 16-bit or 24-bit audio and where the samples start.
5. Plays three 10 second clips of the WAV (`preview_wav.py` and `afplay`)
   and asks whether it sounds like music or static.
6. Adds MD5s for all of it to the manifest.

Everything goes in `backups/`, a [BagIt](https://www.rfc-editor.org/rfc/rfc8493)
bag: the files in `backups/data/` and their checksums in
`backups/manifest-md5.txt`. A third argument names a different bag
directory. `backups/` is git-ignored.

Use a new name for each disc. Running it again with the same name resumes from
that disc's mapfile and only rereads what's missing, which is how to retry a
disc that failed. The disc doesn't count as failed if only the last one or two
sectors are unreadable, which seems to be normal for these CDs.

The tracks are cut out of the WAV by hand, in Audacity or another DAW.

### Dependencies

`rip.sh` only runs on macOS. It checks for each of these when it starts:

| Tool | For | Install |
|---|---|---|
| [GNU ddrescue](https://www.gnu.org/software/ddrescue/) | the raw image | `brew install ddrescue` |
| [cdrdao](https://cdrdao.sourceforge.net/) | the user-data copy | `brew install cdrdao` |
| [uv](https://docs.astral.sh/uv/) | runs `verify_raw.py`, which needs Python 3.11+ and numpy, and installs them itself | `brew install uv` |
| Python 3 | `extract_audio.py` and `preview_wav.py` (standard library only) | `brew install python` |
| `diskutil`, `afplay`, `md5`, `drutil` | disc size and unmounting, the preview, checksums, ejecting | come with macOS |

It was used with GNU ddrescue 1.30, cdrdao 1.2.6, and an Apple USB SuperDrive.

## Working Notes

Using notes from: 

    disktype -d -i disc_image
    Regular file, size 351.4 MiB (368418816 bytes)
    No type and creator code
    Raw CD image, Mode 1

Reading https://bitsgalore.org/2015/11/13/preserving-optical-media-from-the-command-line.html

Then working in Claude led me to

    cdrdao read-cd --datafile backup.bin --driver generic-mmc-raw backup.cue

failed to create the cue file, but then using this worked:

    cdrdao read-toc --driver generic-mmc-raw --datafile backup.bin backup.cue

Forwarded to https://www.mistys-internet.website/blog/blog/2024/09/13/the-working-archivists-guide-to-enthusiast-cd-rom-archiving-tools/

I tried redumper on mac, but it seemed difficult for security reasons. I
downloaded the zip for my old linux laptop, and ran it, `redumper` with no args,
and it detected the cd-drive and went to work:

```
➜  redumper-b720-linux-x86 bin/redumper
redumper (build: b720)
[print usage: --help,-h]
warning: drive not found in the database
warning: using generic drive

drive information
  path: /dev/sg1
  inquiry: PLDS - DVD-RW DS8A8SH (revision level: KU54, vendor specific: 2012/11/14 19:03)
  configuration: GENERIC (read offset: +6, C2 shift: 0, pre-gap start: +0, read method: BE, sector order: DATA_C2_SUB)
  profile: CD-R
  read speed: <optimal>

image path: .
image name: dump_260526_094609_sg1

*** DUMP (time check: 0s)

warning: unable to read CD-TEXT, SCSI (SC: CHECK CONDITION, SK: ILLEGAL REQUEST, ASC: INVALID FIELD IN CDB)
disc TOC:
  track 1 {  data }
    index 01 { LBA:      0, MSF: 00:02:00 }
  track A {  data }
    index 01 { LBA:  62999, MSF: 14:01:74 }
```

I got some [advice](https://digipres.club/@ed/116635874334395478) that pointed
me in the direction of these CDs being a TASCAM DAW backup, which gave Claude
some more to chew on, which can be found in the transcript.md file. It ended up
writing a few utilities for working with the cdrdao output. I should be able to
extract tracks and the mix from the raw wav file that is generated from
`extract_tracks.py`.

## Advice for exporting

I have the TASCAM 788 and CD burner set up. But according to Claude I need to upgrade the firmware to v2.0.2 which allows export of individual tracks to WAV on CD. Then I can rip those on my computer using my CD drive. Apparently the pre-mixes will be lost in the process. Claude also recommended that I copy the raw data from the CDs before doing anything else with them, which is what I was planning on doing anyway using the brute force ripping method from above.

I need to flash the firmware with software from this thread:

https://www.tascamforums.com/threads/tascam-788-firmware-iso-files.8194/

I've put a post on that thread asking and also directly emailed user Bravin to see if he still has it. Unfortunately it doesn't appear to be in the Wayback machine.

## Upgraded

(months pass...)

I heard back and was able to upgrade to 2.02! I tried burning following instructions in the thread, but with Claude finally arrived at this which worked.

```
$ mkdir -p /tmp/fw
$ cp 788_sys.022 /tmp/fw/
$ mkisofs -J -iso-level 1 -V TASCAM788 -o /tmp/788fw.iso /tmp/fw
$ hdiutil burn /tmp/788fw.iso
```

## Backing up

Claude recommended creating a backup of the CDs before attempting to do anything with them in the TASCAM, which makes sense. Here's what I arrived at, based on earlier experiments:

```
cdrdao read-cd --driver generic-mmc-raw --read-raw --datafile disc01.bin disc01.toc
```

Claude ended up writing a little script, since you need to know how much data to convert? It's `rip.sh`.

```
./rip.sh disc01 /dev/disk4
```

This seemed to work, at least for one CD. I put it in backups as `backups/exp_no_1.iso`. I think the checksums file is appended to.

(Later: it hadn't worked. That image, now in `x/`, is scrambled. See
"Backups, take two" below.)

## Reading Backup and Writing WAVs

I'm able to read the CD backups on the TASCAM and listen to them!

I'm able to select Export to WAV, but after assembling the WAVs, the TASCAM "panics" during the Write to CD operation :(

I'm going to roll the dice one more time and buy another CDRW from ebay, and see if that works. If that fails then I'll just rip what I can from the raw files as I was doing originally.


The panic went away when I deleted every song from the TASCAM except the one
being exported. Maybe it was running out of disk space while assembling the
WAVs. So the workflow is: restore one song, export it, delete it, repeat.

## Backups, take two

Ripping the first backup discs turned up a few problems with the original
`rip.sh`:

- Reading `/dev/disk4` (the buffered device) on these discs returns whole
  2352-byte raw sectors, not 2048-byte user data. But the buffer cache gets
  them wrong: about a fifth of the sectors in `x/exp_no_1.iso` are duplicates
  of nearby sectors and as many are missing, while ddrescue reported 100%
  rescued. Reading the uncached `/dev/rdisk4` with `-b 2352` gives every
  sector in order.
- The cdrdao `.bin` (without `--read-raw`) is the 2048-byte user data, the
  opposite of what the script's comments said.
- diskutil's "Disk Size" isn't too big, it's the track counted in 2352-byte
  sectors, so the script takes the size from there and skips the cdrdao TOC
  read (one fewer "disk not readable" dialog per disc).

`backups/` is a [BagIt](https://www.rfc-editor.org/rfc/rfc8493) bag:
payload in `data/`, MD5s in `manifest-md5.txt`. `data/` is git-ignored.
`rip.sh` and the other scripts live in the project root, outside the bag, so
the bag holds only the payload. Run it from the project root:

```
mkdir -p logs && ./rip.sh exp_number_4 /dev/disk4 2>&1 | tee logs/exp_number_4.log
```

A third argument names a different bag directory (default `backups`).

That writes `data/NAME.raw` (raw 2352-byte sectors via ddrescue from
`/dev/rdisk4`), `data/NAME.map` (ddrescue's mapfile) and `data/NAME.bin`
(2048-byte user data via cdrdao), and verifies the `.raw`. Then it extracts
the audio from the `.bin` to `data/NAME.wav` with `extract_audio.py`, plays
three 10 second clips from it and asks whether it sounds like music or static,
and adds all four files to the manifest. Use a new NAME for each disc; reusing
one resumes from that disc's mapfile, which is how to retry a failed disc. You
can pass `/dev/disk4` or `/dev/rdisk4`.

The `.raw` files were called `.iso` until November 2026. They were never ISO
9660 filesystems, just whole raw sectors, so they were renamed.

`extract_audio.py` works out how the samples are stored: some discs are 16-bit
and some 24-bit (all big-endian), and on at least one (`my_girl`) the audio
starts a byte after the end of the FAT region. Read with the wrong width or
alignment, the audio is static. It tries each reading on stretches of the disc
and keeps the one that changes smoothly from sample to sample, the way audio
does. `--bits` and `--skip` override it.

### Verifying

ddrescue's "rescued" percentage only says the reads didn't error, which the
scrambled image also passed. `verify_raw.py` checks every sector instead:

- sync pattern present, and the header address matches its position
- the sector's EDC (its CRC) matches its contents
- optionally, its user data matches the cdrdao `.bin`

```
./verify_raw.py backups/data/exp_number_1.raw --bin backups/data/exp_number_1.bin
```

It runs under [uv](https://docs.astral.sh/uv/), which supplies numpy from the
script's header, so it doesn't depend on which Python is current. The last
one or two sectors of each disc are unreadable, which seems to be normal at the
end of a burned track.

## TASCAM 788 Recovery

I did get the firmware upgrade from the TASCAM website, which let me upgrade
John's TASCAM 788 to get the WAV export option. It is here as 788_sys.022

After buying two different TASCAM 788 CD-RW machines I am unable to reliably
export tracks and mixes without occasional PANIC messages :( I'm going to go
the reverse engineering route and extract a continuous WAV from the cdrdao rip,
and then cut that up in Audacity or a DAW.

The rip.sh program has been updated to generate a backup of the discs,
run cdrdao on it, and then extract the audio, and play a sample to make sure
it's correct. 

