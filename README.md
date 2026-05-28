# JAS CD Recovery

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

