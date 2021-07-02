from .plugin import dir_tmp
from PIL import Image, ImageChops, ImageFile, PngImagePlugin
import re
import sys


_simple_palette = re.compile(b"^\xff*\x00\xff*$")


def mycall(self, cid, pos, length):
    if cid.decode("ascii") == "tRNS":
        return self.chunk_TRNS(pos, length)
    else:
        return getattr(self, "chunk_" + cid.decode("ascii"))(pos, length)


def mychunk_TRNS(self, pos, length):
    s = ImageFile._safe_read(self.fp, length)
    if self.im_mode == "P":
        if _simple_palette.match(s):
            i = s.find(b"\0")
            if i >= 0:
                self.im_info["transparency"] = i
        else:
            self.im_info["transparency"] = s
    elif self.im_mode in ("1", "L", "I"):
        self.im_info["transparency"] = i16(s)
    elif self.im_mode == "RGB":
        self.im_info["transparency"] = i16(s), i16(s, 2), i16(s, 4)
    return s


try:
    pythonVer = sys.version_info.major
except:
    pythonVer = 2

if pythonVer != 2:
    PngImagePlugin.ChunkStream.call = mycall
    PngImagePlugin.PngStream.chunk_TRNS = mychunk_TRNS


def updatePreview(piconSize, imageType, temp):
    width, height = piconSize
    thumbsize = [width, height]

    try:
        im = Image.open(temp)
    except Exception as e:
        print(e)
        print("******* image failed *******")
        preview = ''
        return preview

    # resize / enlarge image - cannot do for picons due to transparency problems.
    if imageType == "cover":
        basewidth = piconSize[0]
        wpercent = (basewidth / float(width))
        hsize = int((float(height) * float(wpercent)))
        im = im.resize((basewidth, hsize), Image.ANTIALIAS)

    imagew, imageh = im.size
    if imagew > width or imageh > height:
        im.thumbnail(thumbsize, Image.ANTIALIAS)

    if imageType == "picon":
        im = im.convert('RGBA')

        # create blank image
        bg = Image.new('RGBA', (width, height), (255, 255, 255, 0))

        # blend background
        imagew, imageh = im.size
        im_alpha = im.convert('RGBA').split()[-1]
        bgwidth, bgheight = bg.size
        bg_alpha = bg.convert('RGBA').split()[-1]
        temp = Image.new('L', (bgwidth, bgheight), 0)
        temp.paste(im_alpha, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)), im_alpha)
        bg_alpha = ImageChops.screen(bg_alpha, temp)
        bg.paste(im, (int((bgwidth - imagew) / 2), int((bgheight - imageh) / 2)))
        im = bg

        # save picon
        preview = dir_tmp + 'original.png'
        im.save(preview, 'PNG')

    return preview
