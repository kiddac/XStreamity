#!/usr/bin/python
# -*- coding: utf-8 -*-

from PIL import Image, ImageChops
from plugin import dir_tmp


def updatePreview(piconSize, imageType, temp):
    width, height = piconSize
    thumbsize = [width, height]

    try:
        im = Image.open(temp)

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
            temp.paste(im_alpha, ((bgwidth - imagew)/2, (bgheight - imageh)/2), im_alpha)
            bg_alpha = ImageChops.screen(bg_alpha, temp)
            bg.paste(im, ((bgwidth - imagew)/2, (bgheight - imageh)/2))
            im = bg

            # save picon
            preview = dir_tmp + 'original.png'
            im.save(preview, 'PNG')

    except:
        preview = ''

    return preview
