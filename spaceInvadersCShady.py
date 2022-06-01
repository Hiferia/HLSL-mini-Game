from asyncio.windows_events import NULL
import glfw
import compushady.config
import compushady.formats
import compushady
from compushady.shaders import hlsl
import struct
import platform
import time


compushady.config.set_debug(True)

print('Using device', compushady.get_current_device().name)

target = compushady.Texture2D(512, 512, compushady.formats.B8G8R8A8_UNORM)



player_ship = [target.width // 2 - 50, target.height -10, 100, 10, 0, 1, 0, 1] 
player_cannon = [target.width //2 - 10, target.height - 20, 20, 20, 0, 1, 0, 1]
projectile = [player_cannon[0], player_cannon[1], 20, 20, 1, 1, 1, 1]
enemy = [target.width // 2 - 50, 5, 100, 10, 1, 0, 0, 1]
enemy_projectile = [enemy[0], enemy[1], 20, 20, 0, 0, 1, 1]

objects_to_draw = [player_ship, player_cannon, enemy]

enemy_direction = 2

enemy_hp = 5
player_hp = 5

speed = 2 

# to support d3d11 we are going to use two buffers here
quads_staging_buffer = compushady.Buffer(16 * 4 * len(objects_to_draw), compushady.HEAP_UPLOAD)
quads_buffer = compushady.Buffer(quads_staging_buffer.size, format=compushady.formats.R32G32B32A32_SINT)

shader = hlsl.compile("""
struct quad_s
{
    uint4 object;
    uint4 color;
};
StructuredBuffer<quad_s> quads : register(t0);
RWTexture2D<float4> target : register(u0);
[numthreads(8, 8, 1)]
void main(int3 tid : SV_DispatchThreadID)
{
    quad_s quad = quads[tid.z];
   
    if (tid.x > quad.object[0] + quad.object[2])
        return;
    if (tid.x < quad.object[0])
        return;
    if (tid.y < quad.object[1])
        return;
    if (tid.y > quad.object[1] + quad.object[3])
        return;
    target[tid.xy] = float4(quad.color);
}
""")

compute = compushady.Compute(shader, srv=[quads_buffer], uav=[target])

# a super simple clear screen procedure
clear_screen = compushady.Compute(hlsl.compile("""
RWTexture2D<float4> target : register(u0);
[numthreads(8, 8, 1)]
void main(int3 tid : SV_DispatchThreadID)
{
    target[tid.xy] = float4(0, 0, 0, 0);
}
"""), uav=[target])

glfw.init()
glfw.window_hint(glfw.CLIENT_API, glfw.NO_API)

window = glfw.create_window(target.width, target.height, 'SpaceInvaders', None, None)

if platform.system() == 'Windows':
    swapchain = compushady.Swapchain(glfw.get_win32_window(
        window), compushady.formats.B8G8R8A8_UNORM, 3)
elif platform.system() == 'Darwin':
    from compushady.backends.metal import create_metal_layer
    ca_metal_layer = create_metal_layer(glfw.get_cocoa_window(window), compushady.formats.B8G8R8A8_UNORM)
    swapchain = compushady.Swapchain(
        ca_metal_layer, compushady.formats.B8G8R8A8_UNORM, 2)
else:
    swapchain = compushady.Swapchain((glfw.get_x11_display(), glfw.get_x11_window(
        window)), compushady.formats.B8G8R8A8_UNORM, 2)


def collide(source, dest):
    if source[0] + source[2] < dest[0]:
        return False
    if source[0] > dest[0] + dest[2]:
        return False
    if source[1] + source[3] < dest[1]:
        return False
    if source[1] > dest[1] + dest[3]:
        return False
    return True

def create_array(objs):
    result = bytes(0)
    for item in objs:        
        buff = struct.pack('8i',*item)        
        result += buff
    return result

def fire_projectile():
    objects_to_draw.append(projectile)
    projectile[0] = player_cannon[0]
    projectile[1] = player_cannon[1] - 20
    
def enemy_fire():
    if enemy_projectile not in objects_to_draw:
        objects_to_draw.append(enemy_projectile)
        enemy_projectile[0] = (int)(enemy[0] + enemy[2] / 2)
        enemy_projectile[1] = enemy[1] + 10

    
def get_inputs():
    if glfw.get_key(window, glfw.KEY_A):
        player_ship[0] -= 2 * speed
        player_cannon[0] -= 2 * speed
    if glfw.get_key(window, glfw.KEY_D):
        player_ship[0] += 2 * speed
        player_cannon[0] += 2 * speed
    if glfw.get_key(window, glfw.KEY_SPACE):
        if projectile not in objects_to_draw:
            fire_projectile()  

def change_color():
    global enemy_hp
    enemy_hp -= 1
    if enemy_hp == 4:
        enemy[5] = 1
    elif enemy_hp == 3:
        enemy[6] = 1
    elif enemy_hp == 2:
        enemy[4] = 0
    elif enemy_hp == 1:
        enemy[5] = 0

            
def collisions():
    if enemy_projectile in objects_to_draw:
        enemy_projectile[1] += 3* speed
        if collide(enemy_projectile, player_ship):
            global player_hp
            player_hp -= 1
            if player_hp == 0:
                objects_to_draw.remove(player_ship)
                objects_to_draw.remove(player_cannon)
            objects_to_draw.remove(enemy_projectile)
        if enemy_projectile[1] > 512:
            objects_to_draw.remove(enemy_projectile)
    if collide(projectile, enemy):
        if enemy in objects_to_draw and projectile in objects_to_draw:
            change_color()
            enemy[2] -= 20
            objects_to_draw.remove(projectile)
            if enemy[2] == 0:
                objects_to_draw.remove(enemy)
                
    
while not glfw.window_should_close(window):
    glfw.poll_events()
    
    get_inputs()
    
    collisions()
    if projectile in objects_to_draw:
        projectile[1] -= 6 * speed
        if projectile[1] < -30:
            objects_to_draw.remove(projectile)
    if enemy in objects_to_draw:
        enemy[0] += enemy_direction * speed
        if enemy[0] < 0:
            enemy_direction = -enemy_direction
            enemy[1] += 20
        elif enemy[0] + enemy[2] > 512:
            enemy_direction = -enemy_direction
            enemy[1] += 20
        enemy_fire()
    
    
    
    clear_screen.dispatch(target.width // 8, target.height // 8, 1)
    
    

    quads_staging_buffer.upload(create_array(objects_to_draw))
    quads_staging_buffer.copy_to(quads_buffer)
    compute.dispatch(target.width // 8, target.height // 8, len(objects_to_draw))
    swapchain.present(target)

swapchain = None  # this ensures the swapchain is destroyed before the window

glfw.terminate()