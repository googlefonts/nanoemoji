from picosvg.svg_transform import Affine2D
from picosvg.svg_types import SVGPath
from nanoemoji.svg_path import SVGPathPen, draw_svg_path
import pytest


class DummyGlyph:
    def draw(self, pen):
        pen.moveTo((0, 0))
        pen.lineTo((0, 10))
        pen.lineTo((10, 10))
        pen.lineTo((10, 0))
        pen.closePath()

        pen.moveTo((0, 15))
        pen.curveTo((0, 20), (10, 20), (10, 15))
        pen.closePath()

        pen.moveTo((0, -5))
        pen.qCurveTo((0, -8), (3, -10), (7, -10), (10, -8), (10, -5))
        pen.endPath()


def test_addComponent_decompose():
    pen = SVGPathPen(glyphSet={"a": DummyGlyph()})
    pen.addComponent("a", Affine2D.identity())

    assert pen.path.d == (
        "M0,0 L0,10 L10,10 L10,0 Z "
        "M0,15 C0,20 10,20 10,15 Z "
        "M0,-5 Q0,-8 1.5,-9 Q3,-10 5,-10 Q7,-10 8.5,-9 Q10,-8 10,-5"
    )


def test_addComponent_decompose_with_transform():
    pen = SVGPathPen(glyphSet={"a": DummyGlyph()})
    pen.addComponent("a", Affine2D(2, 0, 0, 2, 0, 0))

    assert pen.path.d == (
        "M0,0 L0,20 L20,20 L20,0 Z "
        "M0,30 C0,40 20,40 20,30 Z "
        "M0,-10 Q0,-16 3,-18 Q6,-20 10,-20 Q14,-20 17,-18 Q20,-16 20,-10"
    )


def test_draw_onto_existing_path():
    path = SVGPath(d="M0,0 L0,10 L10,10 L10,0 Z")
    pen = SVGPathPen(path=path)

    pen.moveTo((0, 15))
    pen.lineTo((5, 20))
    pen.lineTo((10, 15))
    pen.closePath()

    assert path.d == "M0,0 L0,10 L10,10 L10,0 Z M0,15 L5,20 L10,15 Z"


def test_addComponent_missing():
    pen = SVGPathPen(glyphSet={"a": DummyGlyph()})

    with pytest.raises(KeyError):
        pen.addComponent("b", Affine2D.identity())


@pytest.mark.parametrize(
    "d",
    [
        "M0,0 L0,10 L10,10 L10,0 Z",
        "M0,0 L0,10 L10,10 L10,0",
        "M0,0 L0,10 L10,10 L10,0 Z M12,0 L12,10 L22,10 L22,0",
        "M0,0 L0,10 L10,10 L10,0 M12,0 L12,10 L22,10 L22,0 Z",
        "M0,0 C0,3 2,5 5,5 C8,5 10,3 10,0 C10,-3 8,-5 5,-5 C2,-5 0,-3 0,0 Z",
        "M0,0 Q0,10 10,10 Q20,10 20,0 Z",
    ],
)
def test_roundtrip_path_with_pen(d):
    path = SVGPath(d=d)
    pen = SVGPathPen()
    draw_svg_path(path, pen)
    assert pen.path.d == d
