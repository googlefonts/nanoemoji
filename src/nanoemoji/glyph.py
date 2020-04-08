_MAX_NAME_LEN = 63  # fea for some reason insists on this


def _name(cp):
    ch = chr(cp)
    if ch.isalpha() and ch.isascii():
        return ch
    return "%x" % cp


def glyph_name(codepoints):
    try:
        iter(codepoints)
    except TypeError:
        codepoints = [codepoints]
    name = "_".join((_name(c) for c in codepoints))
    if len(name) > _MAX_NAME_LEN:
      import hashlib
      import base64
      hash = hashlib.sha1()  # don't care if secure
      hash.update(name.encode('utf-8'))
      name = base64.b32encode(hash.digest()).decode('utf-8')
    if not name[0].isalpha():
      name = 'g_' + name
    return name
