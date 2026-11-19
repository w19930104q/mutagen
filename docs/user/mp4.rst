===
MP4
===

There is no MPEG-4 iTunes metadata standard. Mutagen's features are
known to lead to problems in other implementations. For example, FAAD
will crash when reading a file with multiple "tmpo" atoms. iTunes
itself is our main compatibility target.


Chapters
^^^^^^^^

Chapters stored in the ``moov.udta.chpl`` box are exposed as a mutable
sequence on :class:`mutagen.mp4.MP4` through the ``chapters`` attribute
(or ``None`` if the file has no chapter box). Each entry is a
:class:`mutagen.mp4.Chapter` with a ``start`` time in seconds and a
``title`` string. The list can be edited in place or replaced wholesale,
and the changes are written to the file together with the tags on the
next ``save()``::

    from mutagen.mp4 import MP4, Chapter

    audio = MP4("example.m4b")

    # edit in place
    audio.chapters[0] = Chapter(0.0, "Introduction")
    audio.chapters.append(Chapter(120.0, u"第二章"))
    audio.save()

    # replace every chapter, or remove them all with an empty list
    audio.chapters = [Chapter(0.0, "Start"), Chapter(60.0, "End")]
    audio.save()


Compatibility / Bugs
^^^^^^^^^^^^^^^^^^^^

* Prior to 1.16, the MP4 cover atom used a .format attribute to indicate
  the image format (JPEG/PNG). Python 2.6 added a str.format method which
  conflicts with this. 1.17 provides .imageformat when running on any version,
  and still provides .format when running on a version before 2.6.
