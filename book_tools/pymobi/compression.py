import struct


class Uncompression(object):
    def pack(self, data):
        return data

    def unpack(self, data):
        return data


class Palmdoc(object):
    def pack(self, i):
        raise ValueError("not implement")

    def unpack(self, i):
        o, p = "", 0
        while p < len(i):
            c = ord(i[p])
            p += 1
            if c >= 1 and c <= 8:
                o += i[p : p + c]
                p += c
            elif c < 128:
                o += chr(c)
            elif c >= 192:
                o += " " + chr(c ^ 128)
            else:
                if p < len(i):
                    c = (c << 8) | ord(i[p])
                    p += 1
                    m = (c >> 3) & 0x07FF
                    n = (c & 7) + 3
                    if m > n:
                        o += o[-m : n - m]
                    else:
                        for z in range(n):
                            o += o[-m]
        return o

    def unpack3(self, i):
        o, p = b"", 0
        while p < len(i):
            c = i[p]
            p += 1
            if c >= 1 and c <= 8:
                o += i[p : p + c]
                p += c
            elif c < 128:
                o += c.to_bytes(1, "big")
            elif c >= 192:
                o += b" " + (c ^ 128).to_bytes(1, "big")
            else:
                if p < len(i):
                    c = (c << 8) | i[p]
                    p += 1
                    m = (c >> 3) & 0x07FF
                    n = (c & 7) + 3
                    if m > n:
                        o += o[-m : n - m]
                    else:
                        for z in range(n):
                            o += o[-m].to_bytes(1, "big")
        return o


class Huffcdic(object):
    q = struct.Struct(">Q").unpack_from

    def loadHuff(self, huff):
        if huff[0:8] != "HUFF\x00\x00\x00\x18":
            raise ValueError("invalid huff header")
        off1, off2 = struct.unpack_from(">LL", huff, 8)

        def dict1_unpack(v):
            codelen, term, maxcode = v & 0x1F, v & 0x80, v >> 8
            assert codelen != 0
            if codelen <= 8:
                assert term
            maxcode = ((maxcode + 1) << (32 - codelen)) - 1
            return (codelen, term, maxcode)

        self.dict1 = map(dict1_unpack, struct.unpack_from(">256L", huff, off1))

        dict2 = struct.unpack_from(">64L", huff, off2)
        self.mincode, self.maxcode = (), ()
        for codelen, mincode in enumerate((0,) + dict2[0::2]):
            self.mincode += (mincode << (32 - codelen),)
        for codelen, maxcode in enumerate((0,) + dict2[1::2]):
            self.maxcode += (((maxcode + 1) << (32 - codelen)) - 1,)

        self.dictionary = []

    def loadCdic(self, cdic):
        if cdic[0:8] != "CDIC\x00\x00\x00\x10":
            raise ValueError("invalid cdic header")
        phrases, bits = struct.unpack_from(">LL", cdic, 8)
        n = min(1 << bits, phrases - len(self.dictionary))
        h = struct.Struct(">H").unpack_from

        def getslice(off):
            (blen,) = h(cdic, 16 + off)
            slice = cdic[18 + off : 18 + off + (blen & 0x7FFF)]
            return (slice, blen & 0x8000)

        self.dictionary += map(getslice, struct.unpack_from(">%dH" % n, cdic, 16))

    def pack(self, i):
        raise ValueError("not implement")

    def unpack(self, data):
        q = Huffcdic.q

        bitsleft = len(data) * 8
        data += "\x00\x00\x00\x00\x00\x00\x00\x00"
        pos = 0
        (x,) = q(data, pos)
        n = 32

        s = ""
        while True:
            if n <= 0:
                pos += 4
                (x,) = q(data, pos)
                n += 32
            code = (x >> n) & ((1 << 32) - 1)

            codelen, term, maxcode = self.dict1[code >> 24]
            if not term:
                while code < self.mincode[codelen]:
                    codelen += 1
                maxcode = self.maxcode[codelen]

            n -= codelen
            bitsleft -= codelen
            if bitsleft < 0:
                break

            r = (maxcode - code) >> (32 - codelen)
            slice, flag = self.dictionary[r]
            if not flag:
                self.dictionary[r] = None
                slice = self.unpack(slice)
                self.dictionary[r] = (slice, 1)
            s += slice
        return s
