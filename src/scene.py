from turtle import color

from ursina import *
from ursina.shaders import lit_with_shadows_shader
from direct.actor.Actor import Actor
from pathlib import Path

# Deactivate PNMImage warnings (related to textures in GLTF)
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'notify-level-pnmimage error')

class Decor(Entity):
    def __init__(self, model_name):
        super().__init__(
            model=f"{model_name}.glb",
            shader=lit_with_shadows_shader,
            shadows=True,
            cast_shadows=True,
            position=(0, 0, 0),
            scale=1,
            collider = 'mesh'
        )
        print(f"Decor '{model_name}' ready.")

class Character(Entity):
    def __init__(self, model_name, base_path):
        # Basic Setup
        super().__init__(
            model='cube',
            scale=1,
            shader=lit_with_shadows_shader,
            shadows = True,
            color=color.red,alpha=0.5,
            rotation=(0,45,0),
            position=(0,2,0),
            cast_shadows=True
        )
        
        char_full_path = base_path / "assets" / f"{model_name}.glb"
        try:
            self.actor = Actor(str(char_full_path))
            self.actor.reparent_to(self)
            
            for part in self.actor.findAllMatches("**/+GeomNode"):
                part.set_shader(lit_with_shadows_shader)
        except Exception as e:
            print(f"Erreur Character: {e}")

        self.animations_map = {"reflechir": "think", "parler": "talk", "idle": "idle"}

    def play_anim(self, name):
        if name in self.animations_map:
            self.actor.stop()
            self.actor.loop(self.animations_map[name])

class SceneManager:
    def __init__(self, char_name, decor_name):
        self.app = Ursina()
        
        # Setup PATHS
        BASE_DIR = Path(__file__).resolve().parent.parent
        application.asset_folder = BASE_DIR

        window.title = "Ursina POO"
        window.color = color.black
        window.size = (512, 512)

        # --- Lights ---
        self.light_pivot = Entity()
        self.sun = DirectionalLight(parent=self.light_pivot, y=20, x=10, shadows=True)
        self.sun.shadow_map_res = 2048
        self.sun.look_at(Vec3(0,0,0))
        self.sun.color = color.white
        ##AmbientLight(color=color.orange, intensity=0.1)

        # --- Create Instances ---
        self.decor = Decor("Decor")
        self.object = Decor("Object")

        self.player = Character(char_name, BASE_DIR)

        # --- INTERFACE ---
        self.input_field = InputField(label='Anim:', position=(0, -0.45))
        self.input_field.on_submit = self.handle_input

        # --- Camera ---
        camera.fov = 50
        camera.position = (0, 10, -20)
        camera.look_at(Vec3(0,0,0))

    def handle_input(self):
        cmd = self.input_field.text.lower().strip()
        self.player.play_anim(cmd)
        self.input_field.text = ""
        self.input_field.active = False

    def run(self):
        self.app.run()

# La fonction globale update d'Ursina appelle automatiquement les méthodes update des classes
def update():
    if not scene.input_field.active:
        move_speed = 10 * time.dt
        if held_keys['up arrow']:    scene.player.z += move_speed
        if held_keys['down arrow']:  scene.player.z -= move_speed
        if held_keys['left arrow']:  scene.player.x -= move_speed
        if held_keys['right arrow']: scene.player.x += move_speed
        if held_keys['page up']:     scene.player.y += move_speed
        if held_keys['page down']:   scene.player.y -= move_speed
        if held_keys['q']: scene.player.rotation_y += 60 * time.dt
        if held_keys['d']: scene.player.rotation_y -= 60 * time.dt
        
        if held_keys['r']: scene.light_pivot.rotation_y += 60 * time.dt
        if held_keys['t']: scene.light_pivot.rotation_y -= 60 * time.dt
    

if __name__ == "__main__":
    scene = SceneManager("Character", "Decor")
    scene.run()