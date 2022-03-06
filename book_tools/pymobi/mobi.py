import os.path
import datetime
import struct
import re
import array
import sys

try:
    from collections import OrderedDict
except:
    from ordereddict import OrderedDict

from book_tools.pymobi.util import hexdump, decodeVarint, toStr, toByte
from book_tools.pymobi import compression

DEBUG = False

# Reader Type Code
pd_file_code = {
    "Adobe Reader": ".pdfADBE",
    "PalmDOC": "TEXtREAd",
    "BDicty": "BVokBDIC",
    "DB (Database program)": "DB99DBOS",
    "eReader 1": "PNRdPPrs",
    "eReader 2": "DataPPrs",
    "FireViewer (ImageViewer)": "vIMGView",
    "HanDBase": "PmDBPmDB",
    "InfoView": "InfoINDB",
    "iSilo": "ToGoToGo",
    "iSilo 3": "SDocSilX",
    "JFile": "JbDbJBas",
    "JFile Pro": "JfDbJFil",
    "LIST": "DATALSdb",
    "MobileDB": "Mdb1Mdb1",
    "MobiPocket": "BOOKMOBI",
    "Plucker": "DataPlkr",
    "QuickSheet": "DataSprd",
    "SuperMemo": "SM01SMem",
    "TealDoc": "TEXtTlDc",
    "TealInfo": "InfoTlIf",
    "TealMeal": "DataTlMl",
    "TealPaint": "DataTlPt",
    "ThinkDB": "dataTDBP",
    "Tides": "TdatTide",
    "TomeRaider": "ToRaTRPW",
    "Weasel": "zTXTGPlm",
    "WordSmith": "BDOCWrdS",
}
compression_type = {
    1: ("no compression", compression.Uncompression),
    2: ("PalmDOC compression", compression.Palmdoc),
    17480: ("HUFF/CDIC compression", compression.Huffcdic),
}
encryption_type = {
    0: "no encryption",
    1: "Old Mobipocket Encryption",
    2: "Mobipocket Encryption",
}
mobi_type = {
    2: "Mobipocket Book",
    3: "PalmDoc Book",
    4: "Audio",
    232: "mobipocket? generated by kindlegen1.2",
    248: "KF8: generated by kindlegen2",
    257: "News",
    258: "News_Feed",
    259: "News_Magazine",
    513: "PICS",
    514: "WORD",
    515: "XLS",
    516: "PPT",
    517: "TEXT",
    518: "HTML",
}
encoding_type = {
    1252: "CP1252 (WinLatin1)",
    65001: "UTF-8",
}
mobi_exth_type = {
    1: "drm_server_id",
    2: "drm_commerce_id",
    3: "drm_ebookbase_book_id",
    100: "author      <dc:Creator>",
    101: "publisher       <dc:Publisher>",
    102: "imprint         <Imprint>",
    103: "description         <dc:Description>",
    104: 'isbn        <dc:Identifier scheme="ISBN">',
    105: "subject     Could appear multiple times     <dc:Subject>",
    106: "publishingdate      <dc:Date>",
    107: "review      <Review>",
    108: "contributor         <dc:Contributor>",
    109: "rights      <dc:Rights>",
    110: 'subjectcode         <dc:Subject BASICCode="subjectcode">',
    111: "type        <dc:Type>",
    112: "source      <dc:Source>",
    113: 'asin    Kindle Paperwhite labels books with "Personal" if they dont have this record.',
    114: "versionnumber",
    115: "sample  0x0001 if the book content is only a sample of the full book",
    116: "startreading    Position (4-byte offset) in file at which to open when first opened",
    117: 'adult   Mobipocket Creator adds this if Adult only is checked on its GUI; contents: "yes"   <Adult>',
    118: 'retail price    As text, e.g. "4.99"    <SRP>',
    119: 'retail price currency   As text, e.g. "USD"     <SRP Currency="currency">',
    121: "KF8 BOUNDARY Offset",
    125: "count of resources",
    129: "KF8 cover URI",
    131: "Unknown",
    200: "Dictionary short name   As text     <DictionaryVeryShortName>",
    201: "coveroffset     Add to first image field in Mobi Header to find PDB record containing the cover image   <EmbeddedCover>",
    202: "thumboffset     Add to first image field in Mobi Header to find PDB record containing the thumbnail cover image",
    203: "hasfakecover",
    204: "Creator Software    Known Values: 1=mobigen, 2=Mobipocket Creator, 200=kindlegen (Windows), 201=kindlegen (Linux), 202=kindlegen (Mac).",
    205: "Creator Major Version",
    206: "Creator Minor Version",
    207: "Creator Build Number",
    208: "watermark",
    209: "tamper proof keys   Used by the Kindle (and Android app) for generating book-specific PIDs.",
    300: "fontsignature",
    401: "clippinglimit   Integer percentage of the text allowed to be clipped. Usually 10.",
    402: "publisherlimit",
    403: "Unknown",
    404: "ttsflag     1 - Text to Speech disabled; 0 - Text to Speech enabled",
    405: "Unknown",
    406: "Unknown",
    407: "Unknown",
    450: "Unknown",
    451: "Unknown",
    452: "Unknown",
    453: "Unknown",
    501: "cdetype  PDOC - Personal Doc; EBOK - ebook; EBSP - ebook sample",
    502: "lastupdatetime",
    503: "updatedtitle",
    504: "asin    I found a copy of ASIN in this record.",
    508: "other title",
    517: "other author",
    522: "other publisher",
    524: "language        <dc:language>",
    525: "alignment   I found horizontal-lr in this record.",
    529: "kindlegen version",
    535: "Creator Build Number",
}


class BookMobi(object):
    """
    Mobi format:
    `Palm Database Format`_

    `MOBI Format`_

    .. _`Palm Database Format`: http://wiki.mobileread.com/wiki/PDB#Palm_Database_Format
    .. _`MOBI Format`: http://wiki.mobileread.com/wiki/MOBI

    mobi record order
    -----------------
    1. first content. normal is 1.
    2. text record
    #. first non-book record
    #. ortographic
    #. indx record
    #. huff/cdic record
    #. first image record
    #. huff/cdic table record
    #. last content record
    #. flis record
    #. fcis record
    #. srcs record
    """

    palmdb_format = [
        ("name", "32s", 0),
        ("attributes", ">H", 32),
        ("version", ">H", 34),
        ("creationDate", ">L", 36),
        ("modificationDate", ">L", 40),
        ("lastbackupDate", ">L", 44),
        ("modificationNumber", ">L", 48),
        ("appInfoID", ">L", 52),
        ("sortInfoID", ">L", 56),
        ("type", "4s", 60),
        ("creator", "4s", 64),
        ("uniqueIDseed", ">L", 68),
        ("nextRecordListID", ">L", 72),
        ("numberOfRecords", ">H", 76),
        # recordInfoList = 8 * numberOfRecords ...
    ]
    palmdoc_format = [
        ("compression", ">H", 0),
        ("unused", ">H", 2),
        ("textLength", ">L", 4),
        ("recordCount", ">H", 8),
        ("recordSize", ">L", 10),
        ("currentPosition", ">L", 12),
        ("encryptionType", ">H", 12),
    ]
    mobi_format = [
        ("identifier", "4s", 16),
        ("headerLength", ">L", 20),
        ("mobiType", ">L", 24),
        ("textEncoding", ">L", 28),
        ("uniqueID", ">L", 32),
        ("fileVersion", ">L", 36),
        ("ortographicIndex", ">L", 40),
        ("inflectionIndex", ">L", 44),
        ("indexNames", ">L", 48),
        ("indexKeys", ">L", 52),
        ("extraIndex0", ">L", 56),
        ("extraIndex1", ">L", 60),
        ("extraIndex2", ">L", 64),
        ("extraIndex3", ">L", 68),
        ("extraIndex4", ">L", 72),
        ("extraIndex5", ">L", 76),
        ("firstNonBookIndex", ">L", 80),
        ("fullNameOffset", ">L", 84),
        ("fullNameLength", ">L", 88),
        ("locale", ">L", 92),
        ("inputLanguage", ">L", 96),
        ("outputLanguage", ">L", 100),
        ("minVersion", ">L", 104),
        ("firstImageIndex", ">L", 108),
        ("huffmanRecordOffset", ">L", 112),
        ("huffmanRecordCount", ">L", 116),
        ("huffmanTableOffset", ">L", 120),
        ("huffmanTableLength", ">L", 124),
        ("exthFlags", ">L", 128),
        ("unknown132", "12s", 132),
        ("unknown144", "16s", 144),
        ("unknown160", ">L", 160),
        ("unknown164", ">L", 164),
        ("drmOffset", ">L", 168),
        ("drmCount", ">L", 172),
        ("drmSize", ">L", 176),
        ("drmFlags", ">L", 180),
        ("unknown184", ">Q", 184),
        ("firstContentRecordNumber", ">H", 192),
        ("lastContentRecordNumber", ">H", 194),
        ("unknown196", ">L", 196),
        ("fcisRecordNumber", ">L", 200),
        ("fcisRecordCount", ">L", 204),
        ("flisRecordNumber", ">L", 208),
        ("flisRecordCount", ">L", 212),
        ("unknown216", "8s", 216),
        ("srcsRecordNumber", ">L", 224),
        ("srcsRecordCount", ">L", 228),
        ("numberOfCompilationDataSections", ">L", 232),
        ("unknown236", ">L", 236),
        ("extraRecordDataFlags", ">L", 240),
        ("indxRecordOffset", ">L", 244),
        ("unknown248", ">L", 248),
        ("unknown252", ">L", 252),
    ]
    header = OrderedDict()
    records = OrderedDict()
    palmdoc = OrderedDict()
    mobi = OrderedDict()
    mobi_exth = OrderedDict()
    book = OrderedDict()
    compression = None

    def __init__(self, file):
        if isinstance(file, str):
            f = open(file, "rb")
        else:
            f = file

        self.f = f
        self.f.seek(0, 0)
        # palm database header
        header = f.read(78)
        for key, u_fmt, offset in self.palmdb_format:
            (value,) = struct.unpack_from(u_fmt, header, offset)
            self.header[key] = value
        # palm database record
        f.seek(78)
        records = f.read(self.header["numberOfRecords"] * 8)
        for count in range(0, self.header["numberOfRecords"]):
            offset, value = struct.unpack_from(">LL", records, count * 8)
            attributes = value & 0xFF000000
            uniqueID = value & 0xFFFFFF
            self.records[count] = (offset, attributes, uniqueID)
        ident = "%s%s" % (toStr(self.header["type"]), toStr(self.header["creator"]))
        self.book["title"] = toStr(self.header["name"])
        self.book["ident"] = ident
        self.book["creationDate"] = self.datetimeFromValue(self.header["creationDate"])
        self.book["modificationDate"] = self.datetimeFromValue(
            self.header["modificationDate"]
        )
        # ebook header
        record0 = self.loadRecord(0)
        if self.isPalmdoc() or self.isMobipocket():
            # palmdoc header
            for key, u_fmt, offset in self.palmdoc_format:
                (value,) = struct.unpack_from(u_fmt, record0, offset)
                self.palmdoc[key] = value
            if self.palmdoc["encryptionType"] == 1:
                (self.palmdoc["type1KeyData"],) = struct.unpack_from(
                    "16s",
                    record0,
                    14,
                )
            self.book["compression"] = self.typeDesc(
                compression_type,
                self.palmdoc["compression"],
            )
            self.book["encryption"] = self.typeDesc(
                encryption_type,
                self.palmdoc["encryptionType"],
            )
        if ident == pd_file_code["MobiPocket"]:
            # mobi header
            record0_length = len(record0)
            for key, u_fmt, offset in self.mobi_format:
                if record0_length < offset:
                    break
                (value,) = struct.unpack_from(u_fmt, record0, offset)
                self.mobi[key] = value
            # encryption type 1 key data?
            if (
                self.palmdoc["encryptionType"] == 2
                and self.mobi["drmOffset"] != 0xFFFFFFFF
            ):
                self.mobi["drmData"] = record0[
                    self.mobi["drmOffset"] : self.mobi["drmOffset"]
                    + self.mobi["drmSize"]
                ]
            if self.palmdoc["encryptionType"] == 1:
                (self.mobi["type1KeyData"],) = struct.unpack_from(
                    "16s",
                    record0,
                    0x10 + self.mobi["headerLength"],
                )
            # exth
            if (
                self.mobi["headerLength"] > 0xE4
                and self.mobi["minVersion"] >= 5
                and self.mobi["exthFlags"] & 0x40
            ):
                # palmdoc length + mobi length
                exth_addr = 0x10 + self.mobi["headerLength"]
                offset = 0
                exthIdent, exthLength, exthCount = struct.unpack_from(
                    ">4sLL",
                    record0,
                    exth_addr,
                )
                if toStr(exthIdent) != "EXTH":
                    hexdump(record0[exth_addr : exth_addr + exthLength])
                    raise Exception("exth header error: %s" % exthIdent)
                offset += 12
                count = 0
                while count < exthCount:
                    recordType, recordLength = struct.unpack_from(
                        ">LL", record0, exth_addr + offset
                    )
                    (data,) = struct.unpack_from(
                        "%ds" % (recordLength - 8), record0, exth_addr + offset + 8
                    )
                    self.mobi_exth[recordType] = data
                    if DEBUG:
                        if not recordType in mobi_exth_type:
                            print(recordType, data, "unknown type")
                    offset += recordLength
                    count += 1
            (title,) = struct.unpack_from(
                "%ds" % self.mobi["fullNameLength"],
                record0,
                self.mobi["fullNameOffset"],
            )
            if title:
                self.book["title"] = toStr(title)
            self.book["version"] = self.mobi["minVersion"]
            self.book["author"] = toStr(
                self.mobi_exth[100] if 100 in self.mobi_exth else "unknown"
            )
            self.book["mobiType"] = self.typeDesc(
                mobi_type,
                self.mobi["mobiType"],
            )
            self.book["encoding"] = self.typeDesc(
                encoding_type,
                self.mobi["textEncoding"],
            )
            self.book["srcs"] = self.mobi["srcsRecordNumber"] != 0xFFFFFFFF

    def __getitem__(self, name):
        return self.book.get(name)

    def __len__(self):
        return len(self.book)

    def __iter__(self):
        return self.book.itervalues()

    def isMobipocket(self):
        return self.book["ident"] == pd_file_code["MobiPocket"]

    def isPalmdoc(self):
        return self.book["ident"] == pd_file_code["PalmDOC"]

    def unpackFunction(self):
        compression_class = compression_type[self.palmdoc["compression"]][1]
        self.compression = compression_class()
        if isinstance(self.compression, compression.Huffcdic):
            rec_huff = self.loadRecord(self.mobi["huffmanRecordOffset"])
            self.compression.loadHuff(rec_huff)
            for c in range(1, self.mobi["huffmanRecordCount"]):
                rec_cdic = self.loadRecord(self.mobi["huffmanRecordOffset"] + c)
                self.compression.loadCdic(rec_cdic)
        if sys.version_info[0] < 3:
            unpack = self.compression.unpack
        else:
            unpack = self.compression.unpack3
        return unpack

    def typeDesc(self, types, value):
        if value in types:
            desc = types[value]
            if isinstance(desc, tuple):
                return desc[0]
            else:
                return desc
        else:
            return "unknown"

    def loadRecord(self, record_index):
        """
        load palm database's record
        """
        offset = self.records[record_index][0]
        self.f.seek(offset)
        if record_index == (self.header["numberOfRecords"] - 1):
            record = self.f.read()
        else:
            offset2 = self.records[record_index + 1][0]
            record = self.f.read(offset2 - offset)
        return record

    def datetimeFromValue(self, value):
        """
        If the time has the top bit set, it's an unsigned 32-bit number counting from 1st Jan 1904
        If the time has the top bit clear, it's a signed 32-bit number counting from 1st Jan 1970.
        """
        flag = value & 0x80000000
        if flag:
            time = datetime.datetime(1904, 1, 1)
        else:
            time = datetime.datetime(1970, 1, 1)
        time += datetime.timedelta(seconds=value)
        return time

    def decrypt(self, record):
        return record

    def imageExt(self, record):
        (ident,) = struct.unpack_from(">L", record, 0)
        if ident == 0x47494638:
            return ".gif"
        elif ident == 0x89504E47:
            return ".png"
        ident = struct.unpack_from(">HHHL", record, 0)
        if ident[3] == 0x4A464946:
            return ".jpg"
        (ident,) = struct.unpack_from(">4s", record, 0)
        return ".%s" % ident

    def saveRecordImage(self, num, basename):
        rec = self.loadRecord(num)
        ext = self.imageExt(rec)
        img_file = "%s%s" % (basename, ext)
        with open(img_file, "wb") as f:
            f.write(rec)
        return os.path.basename(img_file)

    def loadTextResource(self, data, basename):
        def repl(mo):
            img_idx = int(mo.group(1))
            num = img_idx_base + img_idx - 1
            img_basename = "%s_img_%05d" % (basename, img_idx)
            sys.stdout.write(".")
            sys.stdout.flush()
            img_file = self.saveRecordImage(num, img_basename)
            return toByte('<img src="%s"' % img_file)

        print("Dump image")
        img_idx_base = int(self.mobi["firstImageIndex"])
        img_pattern = (
            b"""<img\s+recindex=['"](\d+)['"]""",
            b"""<img\s+src=['"]kindle:embed:(\d+)\?mime=image/jpg['"]""",
        )
        for pattern in img_pattern:
            regex = re.compile(pattern, re.I)
            data = regex.sub(repl, data)
        if self.mobi["textEncoding"] == 65001:
            charset = "utf-8"
        else:
            charset = "cp%d" % self.mobi["textEncoding"]
        data = re.sub(
            b"<head>",
            toByte(
                '<head>\n<meta http-equiv="Content-Type" content="text/html; charset=%s" />'
                % charset
            ),
            data,
            re.I,
        )
        print("")
        return data

    def unpackMobi(self, output_file):
        rec_num = self.palmdoc["recordCount"]
        text_length = self.palmdoc["textLength"]
        unpack = self.unpackFunction()
        data = []
        print("Title: %s" % self.book["title"])
        print("Compression Type: %s" % self.book["compression"])
        print("Encryption Type: %s" % self.book["encryption"])
        print("Dump html/css")
        for rn in range(1, rec_num + 1):
            record = self.loadRecord(rn)
            extraflags = self.mobi["extraRecordDataFlags"] >> 1
            while extraflags & 0x1:
                # the maximum length of trailing entries size is 32.
                (vint,) = struct.unpack_from(">L", record[-4:], 0)
                fint = decodeVarint(vint)
                record = record[:-fint]
                extraflags >>= 1
            if self.mobi["extraRecordDataFlags"] & 0x1:
                # multibyte bytes is the last byte at the end of trailing
                # entries
                (mb_num,) = struct.unpack_from(">B", record[-1:], 0)
                # bit 1-2 is length, 3-8 is unknown. plus 1 size byte
                mb_num = (mb_num & 0x3) + 1
                record = record[:-mb_num]
            record = self.decrypt(record)
            sys.stdout.write(".")
            sys.stdout.flush()
            data.append(unpack(record))
        data_text = b"".join(data)
        data_css = data_text[text_length:]
        data_text = data_text[:text_length]
        sys.stdout.write("html: %d" % text_length)
        basename = os.path.splitext(output_file)[0]
        if data_css:
            sys.stdout.write(" / css: %d" % len(data_css))
            css_filename = "%s.css" % basename
            with open(css_filename, "wb") as f:
                f.write(data_css)
            data_text = re.sub(
                r"""<head>""",
                '<head>\n<link rel="stylesheet" href="%s" type="text/css"/>'
                % os.path.basename(css_filename),
                data_text,
                re.I,
            )
        print("")
        if self.mobi["firstImageIndex"] != 0xFFFFFFFF:
            data_text = self.loadTextResource(data_text, basename)
        with open(output_file, "wb") as f:
            f.write(data_text)
        # cover
        if 201 in self.mobi_exth:
            print("Dump cover")
            (cover_rn,) = struct.unpack(">L", self.mobi_exth[201])
            cover_rn += self.mobi["firstImageIndex"]
            self.saveRecordImage(cover_rn, "%s_cover" % basename)
        print("Unpack MOBI successfully")

    def unpackMobiCover(self):
        if 201 in self.mobi_exth:
            (cover_rn,) = struct.unpack(">L", self.mobi_exth[201])
            cover_rn += self.mobi["firstImageIndex"]
            rec = self.loadRecord(cover_rn)
            return rec
        return None

    def removeSrcs(self, outmobi, outsrcs=None):
        srcs_rn = self.mobi["srcsRecordNumber"]
        srcs_rc = self.mobi["srcsRecordCount"]
        print("Title: %s" % self.book["title"])
        if srcs_rn == 0xFFFFFFFF or srcs_rc == 0:
            print("No SRCS section.")
            return
        print("Find SRCS: %d" % srcs_rn)
        if outsrcs:
            print("Output ZIP file: %s " % outsrcs)
            f = open(outsrcs, "wb")
            for rn in range(srcs_rn, srcs_rn + srcs_rc):
                sys.stdout.write(".")
                sys.stdout.flush()
                rec = self.loadRecord(rn)
                header = struct.unpack_from(">4L", rec, 0)
                if header[0] == 0x53524353:
                    # SRCS
                    f.write(rec[16:])
            f.close()
        print("")
        print("Output MOBI file: %s" % outmobi)
        with open(outmobi, "wb") as f:
            self.f.seek(0)
            f.write(self.f.read(78))
            # replace srcs section with 2-zero bytes
            recordlist_data = array.array(
                "B", self.f.read(8 * self.header["numberOfRecords"])
            )
            print("Fix record offset")
            srcs_offset = self.records[srcs_rn][0]
            for count in range(0, srcs_rc):
                sys.stdout.write(".")
                sys.stdout.flush()
                fix_offset = srcs_offset + count * 2
                struct.pack_into(
                    ">L", recordlist_data, (srcs_rn + count) * 8, fix_offset
                )
            offset = self.records[srcs_rn + srcs_rc][0] - srcs_offset - srcs_rc * 2
            for rn in range(srcs_rn + srcs_rc, self.header["numberOfRecords"]):
                sys.stdout.write(".")
                sys.stdout.flush()
                fix_offset = self.records[rn][0] - offset
                struct.pack_into(">L", recordlist_data, rn * 8, fix_offset)
            f.write(recordlist_data)
            print("")
            # gap
            gapToDataLength = self.records[0][0] - f.tell()
            if gapToDataLength:
                f.write(self.f.read(gapToDataLength))
            # record
            print("Write record")
            record0 = array.array("B", self.loadRecord(0))
            struct.pack_into(">LL", record0, 224, 0xFFFFFFFF, 0)
            f.write(record0)
            for rn in range(1, srcs_rn):
                sys.stdout.write(".")
                sys.stdout.flush()
                rec = self.loadRecord(rn)
                f.write(rec)
            srcs_data = b"\x00\x00"
            # srcs record
            for rn in range(srcs_rn, srcs_rn + srcs_rc):
                sys.stdout.write(".")
                sys.stdout.flush()
                f.write(srcs_data)
            # record
            for rn in range(srcs_rn + srcs_rc, self.header["numberOfRecords"]):
                sys.stdout.write(".")
                sys.stdout.flush()
                rec = self.loadRecord(rn)
                f.write(rec)
            print("")
        print("Remove SRCS successfully")
