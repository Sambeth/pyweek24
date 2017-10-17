# json-map, a tiled JSON map renderer for pyglet
# Copyright (C) 2014 Juan J. Martinez <jjm@usebox.net>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
A Tiled JSON map renderer for pyglet.

These classes use the JSON format as generated by Tiled JSON plugin.

`pyglet.resource` framework is used to load all the elements of the map, so
any path information must be removed from the tileset.

"""
import os
import json

import pyglet
from pyglet.graphics import OrderedGroup
from pyglet.sprite import Sprite
from pyglet import gl

__all__ = ['Map', "TileLayer", "ObjectGroup",]


def calculate_columns(image_width, tile_width, margin, spacing):
    # works fine for rows too!

    image_width -= margin * 2
    if image_width < tile_width:
        return 0
    if image_width == tile_width:
        return 1
    columns = ((image_width - tile_width) // (tile_width + spacing)) + 1
    assert ((columns * tile_width) + (spacing * (columns  - 1))) == image_width
    return columns


def get_texture_sequence(filename, tilewidth=32, tileheight=32, margin=1, spacing=1, nearest=False):
    """Returns a texture sequence of a grid generated from a tile set."""

    image = pyglet.resource.image(filename)
    region = image.get_region(margin, margin, image.width-margin*2, image.height-margin*2)

    # we've already thrown away the margins
    rows = calculate_columns(region.height, tileheight, margin=0, spacing=spacing)
    cols = calculate_columns(region.width, tilewidth, margin=0, spacing=spacing)

    grid = pyglet.image.ImageGrid(region,
                                  rows,
                                  cols,
                                  row_padding=spacing,
                                  column_padding=spacing,
                                  )


    texture = grid.get_texture_sequence()

    if nearest:
        gl.glTexParameteri(texture.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(texture.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)

    return texture


class BaseLayer(object):
    """
    Base layer.

    Takes care of the "visible" flag.

    """
    # ordered group
    groups = 0

    def __init__(self, data, map):

        self.data = data
        self.map = map

        if self.data["visible"]:
            self.sprites = {}
            self.group = OrderedGroup(BaseLayer.groups)
            BaseLayer.groups += 1


class TileLayer(BaseLayer):
    """
    Tile layer.

    Provides a pythonic interface to the tile layer, including:

        - Iterate through the tiles.
        - Check if one coordinate exists in the layer.
        - Get one tile of layer.

    """
    def __iter__(self):
        return iter(self.data)

    def __contains__(self, index):
        if type(index) != tuple:
            raise TypeError("tuple expected")

        x, y = index
        return int(x+y*self.map.data["width"]) in self.data["data"]

    def __getitem__(self, index):
        if type(index) != tuple:
            raise TypeError("tuple expected")

        x, y = index
        return self.data["data"][int(x+y*self.map.data["width"])]

    def set_viewport(self, x, y, w, h):
        tw = self.map.data["tilewidth"]
        th = self.map.data["tileheight"]

        def yrange(f, t, s):
            while f < t:
                yield f
                f += s

        in_use = set()
        for j in yrange(y, y+h+th, th):
            py = j//th
            for i in yrange(x, x+w+tw, tw):
                px = i//tw
                coordinate = (px, py)
                in_use.add(coordinate)
                if coordinate not in self.sprites:
                    try:
                        texture = self.map.get_texture(self[coordinate])
                        sprite = Sprite(texture,
                                        x=(px*tw),
                                        y=h-(py*th)-th,
                                        batch=self.map.batch,
                                        group=self.group,
                                        usage="static",
                                        )
                    except (KeyError, IndexError):
                        sprite = None
                    self.sprites[coordinate] = sprite

        unused_keys = set(self.sprites) - in_use
        for key in unused_keys:
            o = self.sprites.pop(key)
            if o is not None:
                o.delete()


class ObjectGroup(BaseLayer):
    """
    Object Group Layer.

    Only tile based objects will be drawn (not shape based).

    Provides a pythonic interface to the object layer, including:

        - Iterate through the objects.
        - Check if one coordinate or an object name exists in the layer.
        - Get one object based on its coordinates or its name.

    Also it is possible to get a list of objects of the same type with
    `ObjectGroup.get_by_type(type)`.

    """
    def __init__(self, data, map):
        super(ObjectGroup, self).__init__(data, map)

        self.h = 0
        self.objects = []
        self._index = {}
        self._index_type = {}
        self._xy_index = {}

        for obj in data["objects"]:
            self.objects.append(obj)

            name = obj.get("name", "?")
            if name not in self._index:
                self._index[name] = []

            otype = obj.get("type", "?")
            if otype not in self._index_type:
                self._index_type[otype] = []

            x = int(obj["x"])//self.map.data["tilewidth"]
            y = int(obj["y"])//self.map.data["tileheight"]-1
            coordinate = (x, y)
            if coordinate not in self._xy_index:
                self._xy_index[coordinate] = []

            self._index[name].append(obj)
            self._index_type[otype].append(obj)
            self._xy_index[coordinate].append(obj)

        # XXX: is this useful AT ALL?
        self.objects.sort(key=lambda obj: obj["x"]+obj["y"]*self.map.data["width"])

    def __iter__(self):
        return iter(self.objects)

    def __contains__(self, name):
        if isinstance(name, tuple):
            x, y = name
            return (int(x), int(y)) in self._xy_index
        return name in self._index

    def __getitem__(self, name):
        if isinstance(name, tuple):
            x, y = name
            # XXX: if there are several objects, expect the first one
            return self._xy_index[int(x), int(y)][0]
        return self._index[name]

    def get_by_type(self, otype):
        return self._index_type[otype]

    def set_viewport(self, x, y, w, h):
        self.h = h
        tw = self.map.data["tilewidth"]
        th = self.map.data["tileheight"]

        in_use = set()
        for obj in self.objects:
            if x-tw < obj["x"] < x+w+tw and y-th < obj["y"] < y+h+th:
                if not obj["visible"]:
                    continue
                gid = obj.get("gid")
                if gid:
                    coordinate = (obj["x"], obj["y"])
                    in_use.add(coordinate)
                    try:
                        texture = self.map.get_texture(gid)
                        tileoffset = self.map.get_tileoffset(gid)
                        sprite = Sprite(texture,
                                        x=obj["x"]+tileoffset[0],
                                        y=self.h-obj["y"]+tileoffset[1],
                                        batch=self.map.batch,
                                        group=self.group,
                                        usage="static",
                                        )
                    except (IndexError, KeyError):
                        sprite = None

                    self.sprites[coordinate] = sprite

        unused_keys = set(self.sprites) - in_use
        for key in unused_keys:
            o = self.sprites.pop(key)
            o.delete()


class Tileset(object):
    """Manages a tileset and it's used internally by TileLayer."""
    def __init__(self, data, nearest=False):
        self.data = data

        # used to convert coordinates of the grid
        self.columns = calculate_columns(self.data["imagewidth"], self.data["tilewidth"], spacing=self.data["spacing"], margin=self.data["margin"])
        self.rows = calculate_columns(self.data["imageheight"], self.data["tileheight"], spacing=self.data["spacing"], margin=self.data["margin"])

        # the image will be accessed using pyglet resources
        self.image = os.path.basename(self.data["image"])
        self.texture = get_texture_sequence(self.image, self.data["tilewidth"],
                                            self.data["tileheight"],
                                            self.data["margin"],
                                            self.data["spacing"],
                                            nearest=False,
                                            )

    def __getitem__(self, index):
        return self.texture[index]

    def __len__(self):
        return len(self.texture)


class Map(object):
    """
    Load, manage and render Tiled JSON files.

    Maps can created providing the JSON data to this class or using `Map.load_json()`
    and after that a viewport must be set with `Map.set_viewport()`.
    """

    def __init__(self, data, nearest=False):
        self.data = data

        self.tilesets = {} # the order is not important

        self.layers = []
        self.tilelayers = {}
        self.objectgroups = {}

        for tileset in data["tilesets"]:
            self.tilesets[tileset["name"]] = Tileset(tileset, nearest)

        for layer in data["layers"]:
            # TODO: test this!
            if layer['name'] in (self.tilelayers, self.objectgroups):
                raise ValueError("Duplicated layer name %s" % layer["name"])

            if layer["type"] == "tilelayer":
                self.layers.append(TileLayer(layer, self))
                self.tilelayers[layer["name"]] = self.layers[-1]
            elif layer["type"] == "objectgroup":
                self.layers.append(ObjectGroup(layer, self))
                self.objectgroups[layer["name"]] = self.layers[-1]
            else:
                raise ValueError("unsupported layer type %s, skipping" % layer["type"])

        self.batch = pyglet.graphics.Batch()

        # viewport
        self.x = 0
        self.y = 0
        self.w = 0
        self.h = 0

        # focus
        self.fx = None
        self.fy = None

        # useful (size in pixels)
        self.p_width = self.data["width"]*self.data["tilewidth"]
        self.p_height = self.data["height"]*self.data["tileheight"]

        # build a texture index converting pyglet indexing of the texture grid
        # to tiled coordinate system
        self.tileoffset_index = {}
        self.texture_index = {}
        for tileset in self.tilesets.values():
            for y in range(tileset.rows):
                for x in range(tileset.columns):
                    self.texture_index[x+y*tileset.columns+tileset.data["firstgid"]] = \
                            tileset[(tileset.rows-1-y),x]

                    # TODO: test this!
                    if "tileoffset" in tileset.data:
                        self.tileoffset_index[x+y*tileset.columns+tileset.data["firstgid"]] = \
                                (tileset.data["tileoffset"]["x"], tileset.data["tileoffset"]["y"])

    def invalidate(self):
        """Forces a batch update of the map."""
        self.set_viewport(self.x, self.y, self.w, self.h, True)

    def set_viewport(self, x, y, w, h, force=False):
        """
        Sets the map viewport to the screen coordinates.

        Optionally the force flag can be used to update the batch even if the
        viewport didn't change (this should be used via `Map.invalidate()`).
        """
        # x and y can be floats
        vx = max(x, 0)
        vy = max(y, 0)
        vx = min(vx, (self.p_width)-w)
        vy = min(vy, (self.p_height)-h)
        vw = int(w)
        vh = int(h)

        if not any([force, vx!=self.x, vy!=self.y, vw!=self.w, vh!=self.h]):
            return

        self.x = vx
        self.y = vy
        self.w = vw
        self.h = vh

        for layer in self.layers:
            if layer.data["visible"]:
                layer.set_viewport(self.x, self.y, self.w, self.h)

    def set_focus(self, x, y=None):
        """Sets the focus in (x, y) world coordinates."""
        if y == None:
            y = int(x[1])
            x = int(x[0])
        else:
            x = int(x)
            y = int(y)
        if self.fx == x and self.fy == y:
            return

        self.fx = x
        self.fy = y

        vx = max(x-(self.w//2), 0)
        vy = max(y-(self.h//2), 0)

        if vx+(self.w//2) > self.p_width:
            vx = self.p_width-self.w

        if vy+(self.h//2) > self.p_height:
            vy = self.p_height-self.h

        self.set_viewport(vx, vy, self.w, self.h)

    def world_to_screen(self, x, y):
        """
        Translate world coordinate into screen coordinates.

        Returns a (x, y) tuple.
        """
        return x-self.x, self.h-(y-self.y)

    def get_texture(self, gid):
        """
        Returns a texture identified by its gid.

        If not found will raise a KeyError or IndexError.
        """
        return self.texture_index[gid]

    def get_tileoffset(self, gid):
        """Returns the offset of a tile."""
        return self.tileoffset_index.get(gid, (0, 0))

    @property
    def last_group(self):
        """
        The last use group in `Map` batch.

        This is useful in case any Sprite is added to the `Map` to
        be drawn by the Map's batch without being managed by the Map.

        Using this value plus one will ensure the sprite will be drawn
        over the map.
        """
        return BaseLayer.groups-1

    @staticmethod
    def load_json(fileobj, nearest=False):
        """
        Load the map in JSON format.

        This class method return a `Map` object and the file will be
        closed after is read.

        Set nearest to True to set GL_NEAREST for both min and mag
        filters in the tile textures.
        """
        data = json.load(fileobj)
        fileobj.close()
        return Map(data, nearest)

    def __enter__(self):
        gl.glPushMatrix()
        gl.glTranslatef(-self.x, self.y, 0)

    def __exit__(self, *_):
        gl.glPopMatrix()

    def draw(self):
        """Applies transforms and draws the batch."""
        with self:
            self.batch.draw()

