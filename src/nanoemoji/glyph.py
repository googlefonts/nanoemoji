def glyph_name(codepoints):
    try:
        iter(codepoints)
    except TypeError:
        codepoints = [codepoints]
    return "uni" + "_".join(("%04x" % c for c in codepoints))
