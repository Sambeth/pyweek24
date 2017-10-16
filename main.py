# checked in, got from https://github.com/reidrac/pyglet-tiled-json-map.git
import json_map
# built from source, removed "inline" from Group_kill_p in */group.h
import lepton
import math
import os
# pip3.6 install pyglet
import pyglet.resource
import pyglet.window.key
import pymunk
import sys
# pip3.6 install tmx
import tmx
# pip3.6 install wasabi.geom
from wasabi.geom.vector import Vector, v
from wasabi.geom.vector import zero as vector_zero
from wasabi.geom.vector import unit_x as vector_unit_x
from wasabi.geom.vector import unit_y as vector_unit_y


key = pyglet.window.key
EVENT_HANDLED = pyglet.event.EVENT_HANDLED

window = pyglet.window.Window()

pyglet.resource.path = [".", "gfx/kenney_roguelike/Spritesheet"]
pyglet.resource.reindex()



def vector_clamp(v, other):
    if other.x == 0:
        x = 0
    elif other.x < 0:
        x = max(v.x, other.x)
    else:
        x = min(v.x, other.x)

    if other.y == 0:
        y = 0
    elif other.y < 0:
        y = max(v.y, other.y)
    else:
        y = min(v.y, other.y)

    return Vector((x, y))




class Game:
    def __init__(self):
        self.paused = False

        self.pause_label = pyglet.text.Label('[Pause]',
                          font_name='Times New Roman',
                          font_size=64,
                          x=window.width//2, y=window.height//2,
                          anchor_x='center', anchor_y='center')

    def on_draw(self):
        if self.paused:
            self.pause_label.draw()

game = Game()

class Level:
    def __init__(self, basename):
        self.load(basename)

        self.map.set_viewport(0, 0, window.width, window.height)
        self.background_tiles, self.collision_tiles, self.player_position_tiles = (layer.tiles for layer in self.tiles.layers)
        self.upper_left = vector_zero
        self.lower_right = Vector((
            self.tiles.width * self.tiles.tilewidth,
            self.tiles.height * self.tiles.tileheight,
            ))

        self.foreground_sprite_group = pyglet.graphics.OrderedGroup(self.map.last_group + 1)

    def load(self, basename):
        # we should always save the tmx file
        # then export the json file
        # this function will detect that that's true
        json_path = basename + ".json"
        tmx_path = basename + ".tmx"
        try:
            json_stat = os.stat(json_path)
            tmx_stat = os.stat(tmx_path)
        except FileNotFoundError:
            sys.exit(f"Couldn't find both json and tmx for basename {basename}!")

        if tmx_stat.st_mtime >= json_stat.st_mtime:
            sys.exit(f"{json_path} map file out of date! Export JSON from {tmx_path}.")

        with pyglet.resource.file(json_path) as f:
            self.map = json_map.Map.load_json(f)

        self.tiles = tmx.TileMap.load(tmx_path)
        return self.map


    def on_draw(self):
        self.map.draw()

    def position_to_tile_index(self, x, y=None):
        if y is None:
            assert isinstance(x, Vector)
            y = x.y
            x = x.x
        index = int(((y // self.tiles.tileheight) * (self.tiles.width)) + 
            (x // self.tiles.tilewidth))
        assert index < len(self.collision_tiles)
        return index

    def tile_index_to_position(self, index):
        y = (index // self.tiles.width)
        x = index - (y * self.tiles.width) 
        y *= self.tiles.tileheight
        x *= self.tiles.tilewidth
        return Vector((x, y))

    def collision_tile_at(self, x, y=None):
        return self.collision_tiles[self.position_to_tile_index(x, y)].gid


level = Level("prototype")


sin_45degrees = math.sin(math.pi / 4)
vector_45degrees = Vector((sin_45degrees, sin_45degrees))


class Player:
    def __init__(self):
        # determine position based on first nonzero tile
        # found in player starting position layer
        for i, tile in enumerate(level.player_position_tiles):
            if tile.gid:
                # print("FOUND PLAYER TILE AT", i, level.tile_index_to_position(i))
                self.position = level.tile_index_to_position(i)
                break
        else:
            self.position = vector_zero
        # adjust player position
        # TODO why is this what we wanted?!
        self.position += Vector((0, level.tiles.tileheight))

        self.desired_speed = vector_zero
        self.normalized_desired_speed = vector_zero
        self.speed_multiplier = 10
        self.speed = vector_zero
        self.acceleration_frames = 20 # 20/60 of a second to get to full speed
        self.movement_keys = set()
        # coordinate system has (0, 0) at upper left
        self.movement_vectors = {
            key.UP:    vector_unit_y * -1,
            key.DOWN:  vector_unit_y,
            key.LEFT:  vector_unit_x * -1,
            key.RIGHT: vector_unit_x,
            }
        self.movement_opposites = {
            key.UP: key.DOWN,
            key.DOWN: key.UP,
            key.LEFT: key.RIGHT,
            key.RIGHT: key.LEFT
            }

        self.image = pyglet.image.load("player.png")
        self.sprite = pyglet.sprite.Sprite(self.image, batch=level.map.batch, group=level.foreground_sprite_group)

    def calculate_normalized_desired_speed(self):
        if not (self.desired_speed.x and self.desired_speed.y):
            self.normalized_desired_speed = self.desired_speed
        else:
            self.normalized_desired_speed = Vector((self.desired_speed.x * vector_45degrees.x, self.desired_speed.y * vector_45degrees.y))
        self.normalized_desired_speed *= self.speed_multiplier
        # print("normalized desired speed is now", self.normalized_desired_speed)

    def on_key_press(self, symbol, modifiers):
        if game.paused:
            return
        vector = self.movement_vectors.get(symbol)
        if not vector:
            return
        self.movement_keys.add(symbol)
        self.desired_speed += vector
        # if we press RIGHT while we're already pressing LEFT,
        # cancel out the LEFT (and ignore the keyup on it later)
        #
        # TODO:
        # press-and-hold right
        # then, press-and-hold left
        # then, release left
        # you should resume going right!
        opposite = self.movement_opposites[symbol]
        if opposite in self.movement_keys:
            opposite_vector = self.movement_vectors[opposite]
            self.desired_speed -= opposite_vector
            self.movement_keys.remove(opposite)
        self.calculate_normalized_desired_speed()
        return pyglet.event.EVENT_HANDLED

    def on_key_release(self, symbol, modifiers):
        if game.paused:
            return
        vector = self.movement_vectors.get(symbol)
        if not vector:
            return
        if symbol in self.movement_keys:
            self.movement_keys.remove(symbol)
            vector = self.movement_vectors.get(symbol)
            self.desired_speed -= vector
            self.calculate_normalized_desired_speed()
        return pyglet.event.EVENT_HANDLED

    def on_player_move(self):
        self.sprite.x = self.position.x
        self.sprite.y = window.height - self.position.y - 1
        level.map.set_focus(self.position.x, self.position.y)

    def on_update(self, dt):
        # TODO
        # actually use dt here
        # instead of assuming it's 1/60 of a second
        # print("PLAYER UPDATE", self.speed, self.normalized_desired_speed)
        if self.speed != self.normalized_desired_speed:
            delta = self.normalized_desired_speed / self.acceleration_frames
            self.speed += delta
            self.speed = vector_clamp(self.speed, self.normalized_desired_speed)
            # print("SPEED IS NOW", self.speed)
        if self.speed:
            new_position = self.position + self.speed
            x, y = new_position
            if x < level.upper_left.x:
                x = level.upper_left.x
            if y < level.upper_left.y:
                y = level.upper_left.y
            if x > level.lower_right.x:
                x = level.lower_right.x
            if y > level.lower_right.y:
                y = level.lower_right.y
            # now check if we're colliding
            for key in self.movement_keys:
                vector = self.movement_vectors[key] * 8
                tile_position = new_position + vector
                if level.collision_tile_at(tile_position):
                    # throw away movement in bad direction
                    if vector.x:
                        x = self.position.x
                    else:
                        y = self.position.y
            # print("new position", new_position)
            new_position = Vector((x, y))
            if self.position != new_position:
                self.position = new_position
                # print("position now", self.position)
                self.on_player_move()

    def on_draw(self):
        # we're actually drawn as part of the batch for the tiles
        pass


player = Player()
player.on_player_move()



keypress_handlers = {}
def keypress(key):
    def wrapper(fn):
        keypress_handlers[key] = fn
        return fn
    return wrapper


@keypress(key.ESCAPE)
def key_escape(pressed):
    # print("ESC", pressed)
    pyglet.app.exit()

@keypress(key.SPACE)
def key_escape(pressed):
    # print("SPACE", pressed)
    if pressed:
        game.paused = not game.paused

@keypress(key.UP)
def key_up(pressed):
    print("UP", pressed)

@keypress(key.DOWN)
def key_down(pressed):
    print("DOWN", pressed)

@keypress(key.LEFT)
def key_left(pressed):
    print("LEFT", pressed)

@keypress(key.RIGHT)
def key_right(pressed):
    print("RIGHT", pressed)


@keypress(key.LCTRL)
def key_lctrl(pressed):
    print("LEFT CONTROL", pressed)


key_remapper = {
    key.W: key.UP,
    key.S: key.DOWN,
    key.A: key.LEFT,
    key.D: key.RIGHT,
    }


@window.event
def on_key_press(symbol, modifiers):
    # ignoring modifiers for now
    symbol = key_remapper.get(symbol, symbol)
    # calling it manually instead of stacking
    # so we can benefit from remapped keys
    if player.on_key_press(symbol, modifiers) == EVENT_HANDLED:
        return
    handler = keypress_handlers.get(symbol)
    if handler:
        handler(True)
        return EVENT_HANDLED

@window.event
def on_key_release(symbol, modifiers):
    # ignoring modifiers for now
    symbol = key_remapper.get(symbol, symbol)
    # calling it manually instead of stacking
    # so we can benefit from remapped keys
    if player.on_key_release(symbol, modifiers) == EVENT_HANDLED:
        return
    handler = keypress_handlers.get(symbol)
    if handler:
        handler(False)
        return EVENT_HANDLED


@window.event
def on_draw():
    window.clear()
    level.on_draw()
    player.on_draw()
    game.on_draw()
    fire_on_draw()



def on_update(dt):
    player.on_update(dt)

pyglet.clock.schedule_interval(on_update, 1/60.0)

# fireworks
import os
import math
from random import expovariate, uniform, gauss
from pyglet import image
from pyglet.gl import *

from lepton import Particle, ParticleGroup, default_system, domain
from lepton.renderer import PointRenderer
from lepton.texturizer import SpriteTexturizer, create_point_texture
from lepton.emitter import StaticEmitter, PerParticleEmitter
from lepton.controller import Gravity, Lifetime, Movement, Fader, ColorBlender

spark_tex = image.load(os.path.join(os.path.dirname(__file__), 'flare3.png')).get_texture()
spark_texturizer = SpriteTexturizer(spark_tex.id)
trail_texturizer = SpriteTexturizer(create_point_texture(8, 50))

class Kaboom:
    
    lifetime = 5

    def __init__(self):
        color=(uniform(0,1), uniform(0,1), uniform(0,1), 1)
        while max(color[:3]) < 0.9:
            color=(uniform(0,1), uniform(0,1), uniform(0,1), 1)

        spark_emitter = StaticEmitter(
            template=Particle(
                position=(uniform(-50, 50), uniform(-30, 30), uniform(-30, 30)), 
                color=color), 
            deviation=Particle(
                velocity=(gauss(0, 5), gauss(0, 5), gauss(0, 5)),
                age=1.5),
            velocity=domain.Sphere((0, gauss(40, 20), 0), 60, 60))

        self.sparks = ParticleGroup(
            controllers=[
                Lifetime(self.lifetime * 0.75),
                Movement(damping=0.93),
                ColorBlender([(0, (1,1,1,1)), (2, color), (self.lifetime, color)]),
                Fader(fade_out_start=1.0, fade_out_end=self.lifetime * 0.5),
            ],
            renderer=PointRenderer(abs(gauss(10, 3)), spark_texturizer))

        spark_emitter.emit(int(gauss(60, 40)) + 50, self.sparks)

        spread = abs(gauss(0.4, 1.0))
        self.trail_emitter = PerParticleEmitter(self.sparks, rate=uniform(5,30),
            template=Particle(
                color=color),
            deviation=Particle(
                velocity=(spread, spread, spread),
                age=self.lifetime * 0.75))

        self.trails = ParticleGroup(
            controllers=[
                Lifetime(self.lifetime * 1.5),
                Movement(damping=0.83),
                ColorBlender([(0, (1,1,1,1)), (1, color), (self.lifetime, color)]),
                Fader(max_alpha=0.75, fade_out_start=0, fade_out_end=gauss(self.lifetime, self.lifetime*0.3)),
                self.trail_emitter
            ],
            renderer=PointRenderer(10, trail_texturizer))

        pyglet.clock.schedule_once(self.die, self.lifetime * 2)
    
    def reduce_trail(self, dt=None):
        if self.trail_emitter.rate > 0:
            self.trail_emitter.rate -= 1
    
    def die(self, dt=None):
        default_system.remove_group(self.sparks)
        default_system.remove_group(self.trails)

# win = pyglet.window.Window(resizable=True, visible=False)
# win.clear()

def on_resize(width, height):
    """Setup 3D projection for window"""
    glViewport(0, 0, width, height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(70, 1.0*width/height, 0.1, 1000.0)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
# window.on_resize = on_resize

yrot = 0.0


glEnable(GL_BLEND)
glShadeModel(GL_SMOOTH)
glBlendFunc(GL_SRC_ALPHA,GL_ONE)
glHint(GL_PERSPECTIVE_CORRECTION_HINT,GL_NICEST);
glDisable(GL_DEPTH_TEST)

default_system.add_global_controller(
    Gravity((0,-15,0))
)

MEAN_FIRE_INTERVAL = 3.0

def fire(dt=None):
    Kaboom()
    pyglet.clock.schedule_once(fire, expovariate(1.0 / (MEAN_FIRE_INTERVAL - 1)) + 1)

fire()
pyglet.clock.schedule_interval(default_system.update, (1.0/30.0))
pyglet.clock.set_fps_limit(None)

def fire_on_draw():
    global yrot
    # window.clear()
    glPushMatrix()
    glLoadIdentity()
    glTranslatef(0, 0, -100)
    glRotatef(yrot, 0.0, 1.0, 0.0)
    default_system.draw()
    glPopMatrix()
    '''
    glBindTexture(GL_TEXTURE_2D, 1)
    glEnable(GL_TEXTURE_2D)
    glEnable(GL_POINT_SPRITE)
    glPointSize(100);
    glBegin(GL_POINTS)
    glVertex2f(0,0)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 2)
    glEnable(GL_TEXTURE_2D)
    glEnable(GL_POINT_SPRITE)
    glPointSize(100);
    glBegin(GL_POINTS)
    glVertex2f(50,0)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    '''


pyglet.app.run()