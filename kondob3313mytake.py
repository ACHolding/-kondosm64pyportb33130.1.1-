"""AC Kondo's B3313 Py Port 0.2
Original procedural fan prototype, not a ROM/decompilation or complete B3313 port.
Requires only pygame-ce. Run: python cat4kb3313.py
FILES_OFF: no external assets, network, ROM, configuration, or save-file access.
All progress lasts for this session. Python's only imported module is pygame.
Expansion: 32 rooms / 80 stars, red coins, switches, three keepers, caps,
checkpoint flags, cannons, moving platforms, wall kicks, lava and ice.
This is an original fan prototype, not the complete SM64 PC port or B3313 1.0.

WASD/arrows move | Space jump/swim | Shift crouch + Space long jump
Ctrl airborne ground pound | X punch/dive | E enter door/read sign
Q/C or mouse drag orbit | R center camera | Tab map | Esc pause
F3 diagnostics | F11 fullscreen | M mute | Home return to courtyard
"""
import pygame

TITLE = "AC Kondo's B3313 Py Port 0.2"
FILES_OFF = True
V3 = pygame.Vector3
V2 = pygame.Vector2
W, H = 960, 600

def wave(a):
    return V2(1, 0).rotate(a).y

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def shade(c, k):
    return tuple(int(clamp(v*k, 0, 255)) for v in c)

class Audio:
    def __init__(self):
        self.enabled = True
        self.sounds = {}
        try:
            pygame.mixer.init(22050, -16, 1, 512)
            for name, notes in {'jump':[480,640], 'coin':[880,1320],
                                'star':[523,659,784,1047], 'hurt':[180,90],
                                'door':[220,330,440], 'hit':[140,70]}.items():
                data = bytearray()
                for hz in notes:
                    n = 1700
                    for i in range(n):
                        value = int((1 if (i*hz/22050)%1 < .5 else -1)*2200*(1-i/n))
                        data.extend(value.to_bytes(2, 'little', signed=True))
                self.sounds[name] = pygame.mixer.Sound(buffer=data)
        except (pygame.error, NotImplementedError):
            self.enabled = False
    def play(self, name):
        if self.enabled and name in self.sounds:
            self.sounds[name].play()

class Renderer:
    """Near-clipped, backface-culled flat polygon software renderer."""
    def __init__(self, surface):
        self.surface = surface
        self.faces = []
    def begin(self, eye, target, fog):
        self.eye = V3(eye)
        self.forward = (target-eye).normalize()
        self.right = V3(0,1,0).cross(self.forward).normalize()
        self.up = self.forward.cross(self.right)
        self.fog = fog
        self.faces.clear()
    def camera(self, p):
        d = V3(p)-self.eye
        return V3(d.dot(self.right), d.dot(self.up), d.dot(self.forward))
    def project(self, p):
        return (W/2+p.x*650/p.z, H/2-p.y*650/p.z)
    def poly(self, verts, color, double=False):
        verts = [V3(p) for p in verts]
        if not double:
            normal = (verts[1]-verts[0]).cross(verts[2]-verts[0])
            if normal.dot(self.eye-verts[0]) <= 0:
                return
        points = [self.camera(v) for v in verts]
        clipped = []
        for i, b in enumerate(points):
            a = points[i-1]
            if (a.z >= .18) != (b.z >= .18):
                clipped.append(a+(b-a)*((.18-a.z)/(b.z-a.z)))
            if b.z >= .18:
                clipped.append(b)
        if len(clipped) < 3:
            return
        screen = [self.project(p) for p in clipped]
        if (max(p[0] for p in screen)<0 or min(p[0] for p in screen)>W or
            max(p[1] for p in screen)<0 or min(p[1] for p in screen)>H):
            return
        depth = sum(p.z for p in clipped)/len(clipped)
        f = clamp((depth-18)/65, 0, .88)
        c = tuple(int(color[i]*(1-f)+self.fog[i]*f) for i in range(3))
        self.faces.append((depth, screen, c))
    def box(self, x,y,z, sx,sy,sz, color):
        a,b,c,d = x-sx/2,x+sx/2,z-sz/2,z+sz/2
        t = y+sy
        self.poly([(a,t,c),(a,t,d),(b,t,d),(b,t,c)], shade(color,1.15))
        self.poly([(a,y,d),(a,t,d),(a,t,c),(a,y,c)], shade(color,.67))
        self.poly([(b,y,c),(b,t,c),(b,t,d),(b,y,d)], shade(color,.85))
        self.poly([(a,y,c),(a,t,c),(b,t,c),(b,y,c)], shade(color,.75))
        self.poly([(b,y,d),(b,t,d),(a,t,d),(a,y,d)], color)
    def gem(self, x,y,z, size,color, spin=0, star=False):
        pts=[]
        count=10 if star else 6
        for i in range(count):
            v=V2(0, size*(.45 if star and i%2 else 1)).rotate(i*360/count)
            axis=V2(v.x,0).rotate(spin)
            pts.append(V3(x+axis.x,y+v.y,z+axis.y))
        front=V3(x,y,z)+V3(wave(spin),0,wave(spin+90))*.23
        back=V3(x,y,z)-V3(wave(spin),0,wave(spin+90))*.23
        for i in range(count):
            self.poly([pts[i-1],pts[i],front],shade(color,.8+.2*(i%2)),True)
            self.poly([pts[i],pts[i-1],back],color,True)
    def flush(self):
        self.faces.sort(key=lambda f:f[0],reverse=True)
        for _, p,c in self.faces:
            pygame.draw.polygon(self.surface,c,p)

class Room:
    def __init__(self, name, subtitle, sky, floor, size=18, void=False):
        self.name,self.subtitle,self.sky,self.floor = name,subtitle,sky,floor
        self.size,self.void=size,void
        self.blocks=[]
        self.doors=[]
        self.coins=[]
        self.stars=[]
        self.enemies=[]
        self.signs=[]
        self.water=False
        self.spawn=V3(0,0,-9)
    def block(self,x,y,z,sx,sy,sz,c=(159,145,130)):
        self.blocks.append((x,y,z,sx,sy,sz,c))
    def door(self,x,z,target,label,need=0,y=0):
        self.doors.append((x,y,z,target,label,need))
    def coin(self,x,y,z): self.coins.append(V3(x,y,z))
    def star(self,x,y,z): self.stars.append(V3(x,y,z))

def make_world():
    rooms=[]
    r=Room('Castle Courtyard','The front door remembers you.',(100,160,212),(76,143,67),24)
    r.door(0,15,1,'CASTLE')
    r.block(-8,0,16,8,10,4,(194,180,158));r.block(8,0,16,8,10,4,(194,180,158))
    r.block(0,6,16,8,4,4,(194,180,158))
    for x in (-12,12):
        r.block(x,0,16,4,13,6,(183,171,160))
        r.block(x,13,16,5,1,7,(160,53,63))
    for x,z in [(-16,-5),(16,-4),(-17,9),(17,8)]:
        r.block(x,0,z,1,3,1,(117,78,48));r.block(x,3,z,4,4,4,(37,105,62))
    for i in range(6): r.coin(0,1,-5+i*2)
    r.block(-7,0,0,4,1,4);r.block(-10,0,3,3,2.3,3);r.block(-7,0,6,3,3.7,3)
    r.star(-7,5,6)
    r.signs=[(V3(3,0,-7),'Eighty castle stars. Explore three wings, then enter the Observatory.\nE opens doors. Hold right mouse to orbit. Home returns here.')]
    rooms.append(r)
    r=Room('The Lobby','Every painting is a door. Every door is a question.',(36,30,49),(191,178,155))
    r.door(0,-14,0,'COURTYARD');r.door(-12,8,2,'GARDEN');r.door(12,8,3,'AQUARIUM')
    r.door(-12,-5,4,'BASEMENT');r.door(12,-5,5,'STAIRCASE')
    r.door(0,14,7,'OBSERVATORY',80)
    for x in (-15,15):
        for z in (-10,2,12):r.block(x,0,z,1.4,8,1.4,(217,201,173))
    for i in range(5):r.block(-5+i*2,0,7,2, .65+i*.65,3,(163,61,73))
    r.star(3,4.5,7)
    for x in range(-8,9,2):r.coin(x,1,0)
    r.signs=[(V3(0,0,3),'A note in your handwriting:\nThe staircase has two exits. One is above you.')]
    rooms.append(r)
    r=Room('Unfinished Garden','The sky has been painted over.',(143,168,178),(77,130,80),20)
    r.door(0,-15,1,'LOBBY')
    for i in range(6):
        x=-9+(i%3)*5;z=-2+(i//3)*6
        r.block(x,0,z,3,1+i*.65,3,(160,155,122));r.coin(x,2+i*.65,z)
    r.star(1,5.5,4)
    r.enemies=[[-5,0,-7,0],[6,0,7,2],[8,0,-2,4]]
    r.door(15,14,6,'RED HALL')
    rooms.append(r)
    r=Room('Silent Aquarium','There is no glass between you and the water.',(24,72,110),(49,96,120))
    r.water=True;r.door(0,-14,1,'LOBBY')
    for x in (-8,0,8):r.block(x,0,7,3,2,3,(90,121,128))
    r.star(8,5.5,7)
    for i in range(10):r.coin(-9+i*2,2.5+wave(i*40),3)
    r.signs=[(V3(3,0,-11),'Hold Space to swim upward. Shift descends.\nAir returns near the surface.')]
    rooms.append(r)
    r=Room('Below the Castle','Do not trust the floor you cannot see.',(27,20,35),(106,78,92),20,True)
    r.spawn=V3(0,.1,-12)
    for x,y,z,s in [(0,0,-12,7),(-4,.7,-6,4),(1,1.5,-1,4),(-4,2.3,4,4),(1,3.1,9,5)]:
        r.block(x,y-1,z,s,1,s,(126,101,132));r.coin(x,y+1,z)
    r.door(0,-13,1,'LOBBY');r.star(1,4.6,9)
    rooms.append(r)
    r=Room('Almost Endless Stairs','Keep climbing. The room is counting.',(35,25,48),(101,65,84),24)
    r.spawn=V3(0,0,-18);r.door(0,-20,1,'LOBBY')
    for i in range(16):
        z=-13+i*1.6;y=(i+1)*.45
        r.block(0,0,z,5,y,1.65,(157,47,62))
        if i%2==0:r.coin(0,y+1,z)
    r.star(0,8.5,11)
    r.door(0,12,6,'ATTIC',y=7.2)
    r.door(12,-12,2,'GARDEN')
    rooms.append(r)
    r=Room('The Red Hall','You have been here before. Probably.',(66,18,32),(135,49,60),20)
    r.door(0,-15,5,'STAIRS');r.door(-15,12,2,'GARDEN');r.door(15,12,1,'LOBBY')
    for z in (-7,0,7):
        r.block(-7,0,z,3,5,3,(92,34,47));r.block(7,0,z,3,5,3,(92,34,47))
    r.star(0,1.4,13)
    r.enemies=[[0,0,-3,1],[2,0,6,3],[-3,0,10,5]]
    r.signs=[(V3(3,0,-11),'One castle star is made of thirty yellow coins.\nThe Observatory opens when every star is found.')]
    rooms.append(r)
    r=Room('The Observatory','At last, a room that looks back.',(12,18,48),(63,68,109),20)
    r.door(0,-14,1,'LOBBY')
    for i in range(6):r.block(0,0,-5+i*2,7, .5+i*.45,2,(92,110,152))
    r.signs=[(V3(0,3,7),'YOU FOUND THE WAY OUT.\nOr perhaps the way in. Thank you for playing.\nAll eighty stars collected. Explore as long as you like.')]
    rooms.append(r)
    return rooms

class BaseGame:
    def __init__(self):
        pygame.display.init();pygame.font.init()
        self.screen=pygame.display.set_mode((W,H),pygame.RESIZABLE)
        pygame.display.set_caption(TITLE)
        self.canvas=pygame.Surface((W,H))
        self.render=Renderer(self.canvas)
        self.font=pygame.font.Font(None,25);self.small=pygame.font.Font(None,20)
        self.big=pygame.font.Font(None,58)
        self.audio=Audio();self.clock=pygame.time.Clock()
        self.fullscreen=False;self.running=True;self.mode='title'
        self.debug=False;self.map=False;self.time=0;self.yaw=0;self.pitch=3.8
        self.reset()
    def reset(self):
        self.rooms=make_world();self.stars=set();self.coins=set();self.dead=set()
        self.health=8;self.air=10;self.facing=0;self.combo=0;self.last_land=-10
        self.attack=0;self.invulnerable=0;self.jump_buffer=0;self.coyote=0
        self.message='';self.msg_time=0;self.transition=0
        self.enter(0)
    @property
    def room(self):return self.rooms[self.room_id]
    def enter(self,index):
        self.room_id=index;self.pos=V3(self.room.spawn);self.vel=V3()
        self.grounded=False;self.pound=False;self.yaw=0;self.transition=.65
        self.air=10;self.ground_y=self.pos.y;self.say(self.room.subtitle,4)
    def say(self,s,t=3):self.message=s;self.msg_time=t
    def star_count(self):return len(self.stars)
    def star_available(self,index):return True
    def support(self,x,z,ceiling=999):
        h=-100 if self.room.void else 0
        for bx,by,bz,sx,sy,sz,_ in self.room.blocks:
            top=by+sy
            if abs(x-bx)<sx/2+.27 and abs(z-bz)<sz/2+.27 and top<=ceiling+.01:
                h=max(h,top)
        return h
    def jump(self,keys):
        if self.room.water and self.pos.y<5.8:
            self.vel.y=4.8;return
        if self.grounded or self.coyote>0:
            self.combo=self.combo+1 if self.time-self.last_land<.32 else 1
            if self.combo>3:self.combo=1
            self.vel.y=(8.3,10,12)[self.combo-1]
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                d=V2(0,1).rotate(-self.facing)
                self.vel.x,self.vel.z=d.x*14,d.y*14;self.vel.y=6.1
                self.attack=.6
            self.grounded=False;self.coyote=0;self.jump_buffer=0
            self.audio.play('jump')
    def interact(self):
        for x,y,z,target,label,need in self.room.doors:
            if (self.pos-V3(x,y,z)).length()<3.1:
                if self.star_count()<need:self.say('The door needs %d stars. You have %d.'%(need,self.star_count()))
                else:self.audio.play('door');self.enter(target)
                return
        for p,s in self.room.signs:
            if (self.pos-p).length()<4:self.say(s,9);return
    def hurt(self,amount=1):
        if self.invulnerable>0:return
        self.health-=amount;self.invulnerable=1.8;self.audio.play('hurt')
        self.vel.y=6
        if self.health<=0:
            self.health=8;self.enter(0);self.say('The courtyard welcomes you back. Stars remain in memory.')
    def update(self,dt,keys):
        self.time+=dt;self.msg_time=max(0,self.msg_time-dt)
        self.transition=max(0,self.transition-dt)
        self.attack=max(0,self.attack-dt);self.invulnerable=max(0,self.invulnerable-dt)
        self.jump_buffer=max(0,self.jump_buffer-dt)
        if keys[pygame.K_q]:self.yaw-=100*dt
        if keys[pygame.K_c]:self.yaw+=100*dt
        move=V2(int(keys[pygame.K_d] or keys[pygame.K_RIGHT])-int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
                int(keys[pygame.K_w] or keys[pygame.K_UP])-int(keys[pygame.K_s] or keys[pygame.K_DOWN]))
        crouch=keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        swim=self.room.water and self.pos.y<5.8
        if move.length_squared()>0:
            move=move.normalize().rotate(-self.yaw)
            speed=4 if crouch else 8
            if swim:speed=5
            rate=12 if self.grounded else 3
            if self.attack<=0:
                self.vel.x+=(move.x*speed-self.vel.x)*min(1,dt*rate)
                self.vel.z+=(move.y*speed-self.vel.z)*min(1,dt*rate)
            self.facing=-V2(0,1).angle_to(move)
        elif self.grounded or swim:
            self.vel.x*=max(0,1-9*dt);self.vel.z*=max(0,1-9*dt)
        if self.grounded:self.coyote=.1
        else:self.coyote=max(0,self.coyote-dt)
        if self.jump_buffer>0:self.jump(keys)
        if swim:
            self.vel.y+=( (4 if keys[pygame.K_SPACE] else -3 if crouch else -.6)-self.vel.y)*min(1,dt*5)
            self.air-=dt
            if self.air<=0:self.hurt();self.air=1
        else:
            self.vel.y-=24*dt;self.air=min(10,self.air+dt*4)
        if self.pound:self.vel.y=-23
        # Small fixed steps prevent tunnelling through thin platforms and walls.
        for axis in ('x','z'):
            old=getattr(self.pos,axis);setattr(self.pos,axis,old+getattr(self.vel,axis)*dt)
            for bx,by,bz,sx,sy,sz,_ in self.room.blocks:
                if (abs(self.pos.x-bx)<sx/2+.33 and abs(self.pos.z-bz)<sz/2+.33
                    and self.pos.y<by+sy-.02 and self.pos.y+1.5>by+.02):
                    step=by+sy-self.pos.y
                    if self.grounded and 0<step<=.5:self.pos.y=by+sy
                    else:setattr(self.pos,axis,old);setattr(self.vel,axis,0)
        self.pos.x=clamp(self.pos.x,-self.room.size+.5,self.room.size-.5)
        self.pos.z=clamp(self.pos.z,-self.room.size+.5,self.room.size-.5)
        previous=self.pos.y;self.pos.y+=self.vel.y*dt
        floor=self.support(self.pos.x,self.pos.z,previous+.08)
        self.ground_y=floor
        if self.vel.y<=0 and self.pos.y<=floor and previous>=floor-.08:
            if not self.grounded:self.last_land=self.time
            if self.pound:self.audio.play('hit');self.attack=.3
            self.pos.y=floor;self.vel.y=0;self.grounded=True;self.pound=False
        else:self.grounded=False
        if self.vel.y>0:
            for bx,by,bz,sx,sy,sz,_ in self.room.blocks:
                if (abs(self.pos.x-bx)<sx/2+.3 and abs(self.pos.z-bz)<sz/2+.3
                    and previous+1.5<=by and self.pos.y+1.5>by):
                    self.pos.y=by-1.5;self.vel.y=0
        if self.pos.y<-15:
            self.health=max(1,self.health-2);self.enter(self.room_id);self.audio.play('hurt');return
        for i,c in enumerate(self.room.coins):
            key=(self.room_id,i)
            if key not in self.coins and (self.pos+V3(0,.8,0)-c).length()<1.2:
                self.coins.add(key);self.audio.play('coin');self.health=min(8,self.health+1)
                if len(self.coins)>=30 and ('coins',0) not in self.stars:
                    self.stars.add(('coins',0));self.audio.play('star');self.say('COIN STAR! Thirty coins remembered.',5)
        for i,s in enumerate(self.room.stars):
            key=(self.room_id,i)
            if key not in self.stars and self.star_available(i) and (self.pos+V3(0,.9,0)-s).length()<1.5:
                self.stars.add(key);self.health=8;self.audio.play('star')
                self.say('STAR FOUND!  %d / 80  -  The castle shifts.'%self.star_count(),5)
        for i,e in enumerate(self.room.enemies):
            if (self.room_id,i) in self.dead:continue
            ep=self.enemy_pos(e)
            if (self.pos+V3(0,.5,0)-ep).length()<1.3:
                if self.attack>0 or (self.vel.y<-1 and self.pos.y>ep.y+.3):
                    self.dead.add((self.room_id,i));self.vel.y=8;self.audio.play('hit')
                else:self.hurt();away=self.pos-ep;away.y=0
                if self.invulnerable>1.7:
                    away=self.pos-ep;away.y=0
                    if away.length_squared()>0:
                        away=away.normalize()*8;self.vel.x,self.vel.z=away.x,away.z
    def enemy_pos(self,e):return V3(e[0]+wave(self.time*45+e[3]*80)*2,.5,e[2]+wave(self.time*35+e[3]*50))
    def text(self,s,x,y,color=(244,239,218),font=None,center=False):
        f=font or self.font
        im=f.render(s,True,color)
        if center:x-=im.get_width()/2
        self.canvas.blit(f.render(s,True,(12,13,26)),(x+2,y+2));self.canvas.blit(im,(x,y))
    def draw_world(self):
        r=self.room;t=self.time;ren=self.render
        self.canvas.fill(r.sky)
        for y in range(0,H,8):
            pygame.draw.rect(self.canvas,shade(r.sky,.65+.35*(1-y/H)),(0,y,W,8))
        target=self.pos+V3(0,1.1,0)
        offset=V2(0,-9).rotate(-self.yaw)
        eye=target+V3(offset.x,self.pitch,offset.y)
        # Pull orbit camera in before it passes through castle geometry.
        delta=eye-target
        for n in range(1,31):
            p=target+delta*(n/30)
            if any(abs(p.x-x)<sx/2+.2 and y-.2<p.y<y+sy+.2 and abs(p.z-z)<sz/2+.2
                   for x,y,z,sx,sy,sz,_ in r.blocks):
                eye=target+delta*(max(1,n-2)/30);break
        ren.begin(eye,target,r.sky)
        if not r.void:
            for x in range(-r.size,r.size,3):
                for z in range(-r.size,r.size,3):
                    color=shade(r.floor,1 if (x//3+z//3)%2 else .86)
                    ren.poly([(x,0,z),(x,0,z+3),(x+3,0,z+3),(x+3,0,z)],color)
        for b in r.blocks:ren.box(*b)
        # Outward walls are omitted by backface culling: a readable dollhouse view.
        if self.room_id not in (0,2,4,7):
            s=r.size
            for x in range(-s,s,3):
                ren.poly([(x,0,s),(x+3,0,s),(x+3,9,s),(x,9,s)],(117,99,119))
            for z in range(-s,s,3):
                ren.poly([(-s,0,z),(-s,0,z+3),(-s,9,z+3),(-s,9,z)],(112,92,107))
                ren.poly([(s,0,z+3),(s,0,z),(s,9,z),(s,9,z+3)],(112,92,107))
        for x,y,z,d,label,need in r.doors:
            locked=self.star_count()<need
            ren.box(x,y,z,2.8,3.6,.5,(175,137,72) if locked else (83,62,133))
            ren.box(x,y+.3,z-.29,2.2,2.9,.08,(44,35,63))
            ren.gem(x,y+2,z-.4,.55,(250,203,68),t*30,True)
        for p,_ in r.signs:
            ren.box(p.x,p.y,p.z,.18,1.4,.18,(100,70,44))
            ren.box(p.x,p.y+1,p.z,1.3,.8,.16,(189,158,103))
        for i,c in enumerate(r.coins):
            if (self.room_id,i) not in self.coins:ren.gem(c.x,c.y+wave(t*160+i*30)*.12,c.z,.35,(255,205,57),t*150)
        for i,s in enumerate(r.stars):
            if (self.room_id,i) not in self.stars and self.star_available(i):ren.gem(s.x,s.y+wave(t*100)*.2,s.z,.85,(255,218,70),t*65,True)
        for i,e in enumerate(r.enemies):
            if (self.room_id,i) in self.dead:continue
            p=self.enemy_pos(e)
            ren.box(p.x,0,p.z,1.1,.7,.95,(137,81,51));ren.box(p.x-.27,.65,p.z-.49,.19,.25,.08,(250,237,208));ren.box(p.x+.27,.65,p.z-.49,.19,.25,.08,(250,237,208))
        if self.room_id==7:ren.gem(0,5,7,2,(134,208,255),t*25,True)
        p=self.pos
        if self.ground_y>-20:
            y=self.ground_y+.025
            ren.poly([(p.x-.55,y,p.z-.4),(p.x-.55,y,p.z+.4),(p.x+.55,y,p.z+.4),(p.x+.55,y,p.z-.4)],(42,43,50))
        if not(self.invulnerable>0 and int(t*12)%2):
            # Original low-poly plumber avatar, built entirely from colored cuboids.
            stride=wave(t*750)*.21 if self.vel.x**2+self.vel.z**2>1 and self.grounded else 0
            def part(x,y,z,sx,sy,sz,c):
                v=V2(x,z).rotate(-self.facing);ren.box(p.x+v.x,p.y+y,p.z+v.y,sx,sy,sz,c)
            part(-.22,.08,stride,.34,.45,.46,(53,56,107));part(.22,.08,-stride,.34,.45,.46,(53,56,107))
            part(0,.48,0,.72,.55,.48,(41,88,173));part(0,.9,0,.79,.38,.5,(195,51,63))
            part(0,1.25,0,.63,.5,.58,(234,177,130));part(0,1.72,0,.78,.18,.72,(216,57,67))
            part(0,1.27,.34,.4,.12,.12,(66,40,33))
            part(-.56,.75,.4 if self.attack>0 else 0,.27,.35,.3,(239,232,219));part(.56,.75,0,.27,.35,.3,(239,232,219))
        if r.water:
            # Tiled surface keeps painter ordering local instead of one giant polygon.
            for x in range(-18,18,3):
                for z in range(-18,18,3):
                    if (x//3+z//3)%3==0:
                        ren.poly([(x,6,z),(x,6,z+3),(x+3,6,z+3),(x+3,6,z)],(49,129,163))
        ren.flush()
        if r.water and p.y<5.8:
            tint=pygame.Surface((W,H),pygame.SRCALPHA);tint.fill((14,89,152,45));self.canvas.blit(tint,(0,0))
        for x,y,z,d,label,need in r.doors:
            if (p-V3(x,y,z)).length()<3.1:
                self.text('E  /  '+label+('  [%d STARS]'%need if need else ''),W/2,H-95,(255,217,110),center=True)
        for loc,_ in r.signs:
            if (p-loc).length()<4:self.text('E  /  READ',W/2,H-95,(255,217,110),center=True)
    def overlay(self):
        veil=pygame.Surface((W,H),pygame.SRCALPHA);veil.fill((7,10,27,207));self.canvas.blit(veil,(0,0))
    def draw(self):
        self.draw_world()
        if self.mode=='play':
            pygame.draw.rect(self.canvas,(20,24,43),(0,0,W,56))
            self.text('STARS  %02d / 80'%self.star_count(),20,17,(255,213,80))
            self.text('COINS  %02d'%len(self.coins),218,17,(255,213,80))
            self.text(self.room.name,W/2,18,center=True)
            for i in range(8):pygame.draw.circle(self.canvas,(96,207,133) if i<self.health else (59,60,78),(770+i*22,28),8)
            self.text('WASD move   SPACE jump   SHIFT long jump   X attack   E interact   TAB map   ESC pause',W/2,H-27,font=self.small,center=True)
            if self.room.water:self.text('AIR  '+'|'*int(self.air*2),20,70,(146,220,255))
            if self.msg_time>0:
                lines=self.message.split('\n')
                pygame.draw.rect(self.canvas,(24,26,43),(60,H-175,W-120,25*len(lines)+22),border_radius=8)
                for i,s in enumerate(lines):self.text(s,W/2,H-165+i*25,font=self.small,center=True)
            if self.debug:self.text('%.0f FPS | room %d | xyz %.1f %.1f %.1f | polygons %d'%(self.clock.get_fps(),self.room_id,*self.pos,len(self.render.faces)),12,100,font=self.small)
            if self.map:
                self.draw_directory()

        else:
            self.overlay()
            self.text("AC KONDO'S",W/2, 80,(171,201,255),font=self.big,center=True)
            self.text('B3313 PY PORT 0.2',W/2,145,(255,219,122),font=self.big,center=True)
            self.text('An original, procedural castle dream',W/2,213,center=True)
            self.text('ENTER  /  '+('START' if self.mode=='title' else 'RESUME'),W/2,277,(145,225,190),center=True)
            lines=['WASD / arrows: move    Space: jump (chain three jumps)',
                   'Shift + Space: long jump    Ctrl: ground pound    X: punch / dive',
                   'Q / C or right mouse drag: camera    R: center camera',
                   'E: doors / signs    Tab: map    Home: courtyard',
                   'M: sound '+('ON' if self.audio.enabled else 'OFF')+'    F11: fullscreen    F3: diagnostics',
                   '32 rooms. 80 stars. No assets or save files.']
            for i,s in enumerate(lines):self.text(s,W/2,332+i*29,font=self.small,center=True)
            self.text('ESC  /  '+('QUIT' if self.mode=='title' else 'RESUME    |    END: quit'),W/2,540,center=True)
        if self.transition>0 and self.mode=='play':
            v=pygame.Surface((W,H));v.fill((8,10,23));v.set_alpha(int(255*self.transition/.65));self.canvas.blit(v,(0,0))
        sw,sh=self.screen.get_size();scale=min(sw/W,sh/H)
        size=(max(1,int(W*scale)),max(1,int(H*scale)))
        self.screen.fill((0,0,0));self.screen.blit(pygame.transform.scale(self.canvas,size),((sw-size[0])//2,(sh-size[1])//2))
        pygame.display.flip()
    def events(self):
        for e in pygame.event.get():
            if e.type==pygame.QUIT:self.running=False
            elif e.type==pygame.MOUSEMOTION and e.buttons[2] and self.mode=='play':
                self.yaw+=e.rel[0]*.35;self.pitch=clamp(self.pitch+e.rel[1]*.04,1.5,11)
            elif e.type==pygame.KEYDOWN:
                k=e.key
                if k==pygame.K_F11:
                    self.fullscreen=not self.fullscreen
                    self.screen=pygame.display.set_mode((0,0) if self.fullscreen else (W,H),pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE)
                elif k==pygame.K_m:self.audio.enabled=not self.audio.enabled
                elif k==pygame.K_F3:self.debug=not self.debug
                elif k==pygame.K_ESCAPE:
                    if self.mode=='title':self.running=False
                    else:self.mode='play' if self.mode=='pause' else 'pause'
                elif k==pygame.K_RETURN and self.mode!='play':self.mode='play'
                elif k==pygame.K_END and self.mode!='play':self.running=False
                elif self.mode=='play':
                    if k==pygame.K_SPACE:self.jump_buffer=.15
                    elif k==pygame.K_e:self.interact()
                    elif k==pygame.K_r:self.yaw=self.facing
                    elif k==pygame.K_TAB:self.map=not self.map
                    elif k==pygame.K_HOME:self.enter(0)
                    elif k in (pygame.K_LCTRL,pygame.K_RCTRL) and not self.grounded and not self.room.water:self.pound=True
                    elif k==pygame.K_x:
                        self.attack=.4
                        if not self.grounded:
                            d=V2(0,1).rotate(-self.facing);self.vel.x,self.vel.z=d.x*12,d.y*12
                        self.audio.play('hit')
    def run(self):
        while self.running:
            dt=min(self.clock.tick(60)/1000,.05)
            self.events()
            if self.mode=='play' and not self.map:
                keys=pygame.key.get_pressed()
                steps=max(1,int(dt/.008)+1)
                for _ in range(steps):self.update(dt/steps,keys)
            self.draw()
        pygame.quit()



# Expansion content is original: names, geometry, and challenges are not a
# dump or a claimed room-for-room recreation of the B3313 1.0 ROM hack.
COURSES = [
    ('Forgotten Battlefield','meadow',0),
    ('Fortress Without a Flag','stone',1),
    ('Drowned Gallery','water',2),
    ('Clockwork Atrium','clock',3),
    ('Cold Storage Mountain','snow',4),
    ('Basement Furnace','lava',5),
    ('The Unoccupied Ballroom','ghost',6),
    ('Keeper of the First Wing','boss',7),
    ('Courtyard at Midnight','night',0),
    ('Sandstone Memory','sand',1),
    ('Reservoir of Lost Doors','water',2),
    ('Pendulum Archive','clock',3),
    ('Whiteout Balcony','snow',4),
    ('Crimson Industrial Hall','lava',5),
    ('Library of False Windows','ghost',6),
    ('Keeper of the Lower Wing','boss',7),
    ('Garden Above the Ceiling','meadow',0),
    ('The Inverted Monument','stone',1),
    ('Aqueduct at 3 AM','water',2),
    ('The Clock That Never Strikes','clock',3),
    ('Frozen Star Chamber','snow',4),
    ('The Last Boiler','lava',5),
    ('Hall of Unwritten Letters','ghost',6),
    ('Keeper of the Final Wing','boss',7),
]
PALETTES = {
    'meadow':((100,161,192),(75,132,78),(152,151,112)),
    'stone':((89,103,137),(122,124,138),(161,157,145)),
    'water':((24,65,99),(44,90,111),(83,128,145)),
    'clock':((48,38,61),(112,91,69),(164,123,67)),
    'snow':((138,167,200),(187,207,220),(142,174,204)),
    'lava':((80,24,32),(87,52,57),(123,88,81)),
    'ghost':((33,31,51),(83,74,108),(122,106,145)),
    'boss':((47,26,48),(88,72,98),(135,108,139)),
    'night':((17,28,58),(40,73,78),(92,107,119)),
    'sand':((174,124,97),(180,151,95),(191,166,107)),
}

def expand_world(rooms):
    rooms[1].door(0,6,8,'EAST WING')
    rooms[2].door(-14,13,16,'LOWER WING')
    rooms[6].door(0,17,24,'UPPER WING')
    for j,(name,theme,layout) in enumerate(COURSES):
        sky,floor,brick=PALETTES[theme]
        r=Room(name,'A room the blueprints forgot.',sky,floor,24)
        r.theme=theme;r.layout=layout;r.red=[];r.switch=None;r.movers=[]
        r.hazards=[];r.cap=None;r.checkpoint=V3(-4,0,-12)
        r.boss=V3(0,0,9) if layout==7 else None
        r.spawn=V3(0,0,-17)
        r.door(0,-20,1,'LOBBY')
        if j<23:r.door(18,17,9+j,'NEXT ROOM')
        else:r.door(18,17,7,'OBSERVATORY',80)
        if j>0:r.door(-18,17,7+j,'PREVIOUS ROOM')
        # Eight visible red coins can be reached from the safe perimeter.
        for x,z in [(-13,-12),(-13,-4),(-13,4),(-13,12),(13,-12),(13,-4),(13,4),(13,12)]:
            r.red.append(V3(x,1.1,z))
        for i in range(8):r.coin(-7+i*2,1,-11)
        r.signs=[(V3(3,0,-16),'Two course stars and one red-coin star are hidden here.\nBlue flags set a checkpoint. E uses switches and cannons.')]
        if layout==0:
            for i in range(7):
                x=-5+(i%2)*5;z=-6+i*2.8;y=.6+i*.55
                r.block(x,0,z,4,y,4,brick)
            r.star(-5,5.3,10.8);r.star(7,1.3,8)
            r.enemies=[[-6,0,0,1],[7,0,6,4]]
            r.cap=('wing',V3(6,1.1,-8))
        elif layout==1:
            # Broad concentric terraces: each step is within jump range.
            r.block(0,0,4,16,1.1,16,brick)
            r.block(0,1.1,4,11,1.2,11,brick)
            r.block(0,2.3,4,6,1.3,6,brick)
            r.star(0,5,4);r.star(0,1.4,-7)
            r.switch=V3(8,1.1,4)
            r.cap=('metal',V3(-7,1.2,-8))
        elif layout==2:
            r.water=True
            for x,z in [(-7,-3),(0,3),(7,9)]:r.block(x,0,z,4,2.5,4,brick)
            r.star(-7,4,-3);r.star(7,5.4,9)
            r.cap=('metal',V3(6,1,-10))
        elif layout==3:
            for i in range(5):
                y=.5+i*.7;z=-7+i*4
                r.block(0,0,z,3,y,3,brick)
            r.star(0,4.6,9);r.star(-7,1.4,7)
            r.switch=V3(8,0,4)
            for i in range(3):
                idx=len(r.blocks);r.block(5,1+i*.6,-4+i*5,3,.5,3,(198,156,75))
                r.movers.append((idx,5,1+i*.6,-4+i*5,i*90))
        elif layout==4:
            for i in range(7):r.block(-6+i*2,0,-5+i*2.3,4,.5+i*.6,4,brick)
            r.star(6,5.5,8.8);r.star(-8,1.4,8)
            r.cap=('wing',V3(7,1,-9))
        elif layout==5:
            # Lava pools have safe paths around them; metal cap ignores heat.
            r.hazards=[(-6,-2,5,8),(6,5,5,8),(0,12,6,3)]
            for i in range(5):r.block(-3+i*1.5,0,-5+i*3,2.8,.5+i*.65,2.8,brick)
            r.star(3,4.5,7);r.star(-8,1.4,10)
            r.cap=('metal',V3(-7,1,-9))
        elif layout==6:
            for x in (-7,7):
                for z in (-5,2,9):r.block(x,0,z,2,5.5,2,brick)
            r.star(0,1.4,12);r.star(7,1.4,14)
            r.switch=V3(-8,0,14)
            r.cap=('vanish',V3(7,1,-9))
            r.enemies=[[0,0,-1,1],[0,0,7,4]]
        else:
            r.star(-7,1.4,6);r.star(0,1.4,10)
            for x in (-8,8):r.block(x,0,10,2,3,2,brick)
        rooms.append(r)
    return rooms

class Game(BaseGame):
    def reset(self):
        self.visited=set();self.red_coins=set();self.switches=set()
        self.boss_hp={};self.boss_cooldown=0;self.cap_kind='';self.cap_time=0
        self.checkpoints={};self.map_page=0;self.wall_time=0;self.wall_push=V3()
        self.cannon=False;self.cannon_power=18;self.previous_move=V2()
        super().reset()
        self.rooms=expand_world(self.rooms)
        self.total_stars=sum(len(r.stars) for r in self.rooms)+len(COURSES)+1
        assert self.total_stars==80
    def enter(self,index):
        super().enter(index)
        self.visited.add(index)
        self.cannon=False
        if index in self.checkpoints:self.pos=V3(self.checkpoints[index])
        self.boss_hp.setdefault(index,3)
        self.map_page=index//8
    def star_available(self,index):
        if self.room_id<8 or index==0:return True
        if self.room.boss is not None:return self.boss_hp.get(self.room_id,3)<=0
        if self.room.switch is not None:return self.room_id in self.switches
        return True
    def jump(self,keys):
        if self.cap_kind=='wing' and self.cap_time>0 and not self.grounded:
            self.vel.y=9;self.audio.play('jump');self.jump_buffer=0;return
        if self.wall_time>0 and not self.grounded and self.coyote<=0:
            self.vel=self.wall_push*9+V3(0,9,0)
            self.wall_time=0;self.jump_buffer=0;self.audio.play('jump');return
        super().jump(keys)
    def hurt(self,amount=1):
        if self.cap_time>0 and self.cap_kind in ('metal','vanish'):return
        super().hurt(amount)
    def interact(self):
        r=self.room
        if self.cannon:
            d=V2(0,1).rotate(-self.yaw)
            self.vel=V3(d.x*18,self.cannon_power,d.y*18)
            self.pos.y+=.5;self.grounded=False;self.coyote=0
            self.attack=1.4;self.cannon=False;self.audio.play('hit');return
        if self.room_id>=8:
            if r.switch is not None and (self.pos-r.switch).length()<2.5:
                self.switches.add(self.room_id);self.audio.play('door')
                self.say('SWITCH ON! The second course star has appeared.');return
            if (self.pos-V3(7,0,-15)).length()<2.5:
                self.cannon=True;self.vel=V3()
                self.say('CANNON: Q / C aim. Up / Down elevation. E launches.',30);return
        super().interact()
    def update(self,dt,keys):
        if self.cannon:
            self.time+=dt
            self.yaw+=(int(keys[pygame.K_c])-int(keys[pygame.K_q]))*70*dt
            self.cannon_power=clamp(self.cannon_power+(int(keys[pygame.K_UP])-int(keys[pygame.K_DOWN]))*10*dt,9,26)
            return
        r=self.room;rid=self.room_id;oldpos=V3(self.pos);oldvel=V3(self.vel)
        self.wall_time=max(0,self.wall_time-dt)
        self.boss_cooldown=max(0,self.boss_cooldown-dt)
        self.cap_time=max(0,self.cap_time-dt)
        if self.cap_time==0:self.cap_kind=''
        # Carry the player on a platform before the normal collision step.
        for idx,x,y,z,phase in getattr(r,'movers',[]):
            b=r.blocks[idx];nx=x+wave(self.time*55+phase)*3
            if self.grounded and abs(self.pos.x-b[0])<b[3]/2+.25 and abs(self.pos.z-b[2])<b[5]/2+.25 and abs(self.pos.y-(b[1]+b[4]))<.08:
                self.pos.x+=nx-b[0]
            r.blocks[idx]=(nx,y,z,*b[3:])
        super().update(dt,keys)
        if self.room_id!=rid:return
        if getattr(r,'theme','')=='snow' and self.grounded:
            moving=any(keys[k] for k in (pygame.K_w,pygame.K_a,pygame.K_s,pygame.K_d,pygame.K_UP,pygame.K_DOWN,pygame.K_LEFT,pygame.K_RIGHT))
            if not moving:
                self.vel.x=oldvel.x*max(0,1-dt*.6)
                self.vel.z=oldvel.z*max(0,1-dt*.6)
        if self.cap_kind=='wing' and self.cap_time>0 and keys[pygame.K_SPACE] and self.vel.y<0:
            self.vel.y=max(-2,self.vel.y)
        if self.cap_kind=='metal' and self.cap_time>0 and r.water:
            self.air=10
            if not self.grounded:self.vel.y-=35*dt
        if not self.grounded:
            for axis in ('x','z'):
                if abs(getattr(oldvel,axis))>2 and abs(getattr(self.pos,axis)-getattr(oldpos,axis))<.00001:
                    self.wall_time=.15;self.wall_push=V3()
                    setattr(self.wall_push,axis,-1 if getattr(oldvel,axis)>0 else 1)
        if rid<8:return
        if (self.pos-r.checkpoint).length()<1.8 and rid not in self.checkpoints:
            self.checkpoints[rid]=V3(r.checkpoint);self.audio.play('coin');self.say('CHECKPOINT SET - session memory only')
        if r.cap and (self.pos+V3(0,1,0)-r.cap[1]).length()<1.3 and self.cap_time<1:
            self.cap_kind=r.cap[0];self.cap_time=25;self.audio.play('star')
            self.say({'wing':'WING CAP: tap Space in air to flap; hold to glide.',
                      'metal':'METAL CAP: ignore damage and sink safely underwater.',
                      'vanish':'VANISH CAP: enemies cannot hurt you.'}[self.cap_kind],5)
        for i,c in enumerate(r.red):
            if (rid,i) not in self.red_coins and (self.pos+V3(0,.8,0)-c).length()<1.3:
                self.red_coins.add((rid,i));self.audio.play('coin')
                count=sum((rid,k) in self.red_coins for k in range(8))
                self.say('RED COINS  %d / 8'%count,2)
                if count==8:
                    self.stars.add(('red',rid));self.audio.play('star');self.say('RED COIN STAR!  %d / 80'%len(self.stars),4)
        for x,z,sx,sz in r.hazards:
            if abs(self.pos.x-x)<sx/2 and abs(self.pos.z-z)<sz/2 and self.pos.y<.3:self.hurt(2)
        if r.boss is not None and self.boss_hp[rid]>0:
            boss=self.boss_position()
            if (self.pos+V3(0,.8,0)-boss).length()<2.2:
                if (self.attack>0 or (self.vel.y<-1 and self.pos.y>boss.y+.5)) and self.boss_cooldown<=0:
                    self.boss_hp[rid]-=1;self.boss_cooldown=1.3
                    self.vel.y=10;self.audio.play('hit')
                    if self.boss_hp[rid]==0:self.say('KEEPER DEFEATED! The second star has appeared.',5)
                    else:self.say('KEEPER  %d / 3 HP'%self.boss_hp[rid],2)
                elif self.boss_cooldown<=0:self.hurt(2)
    def boss_position(self):
        p=self.room.boss
        return p+V3(wave(self.time*45)*3,1,wave(self.time*33)*2)
    def draw_world(self):
        # Insert dynamic world objects before the base renderer flushes.
        renderer=self.render;normal_flush=renderer.flush
        def flush_expansion():
            r=self.room;t=self.time;ren=self.render
            if self.room_id>=8:
                for i,c in enumerate(r.red):
                    if (self.room_id,i) not in self.red_coins:ren.gem(c.x,c.y,c.z,.42,(250,62,79),t*130)
                for x,z,sx,sz in r.hazards:
                    ren.box(x,.02,z,sx,.06,sz,(235,89+int(wave(t*100)*20),35))
                if r.switch is not None:
                    p=r.switch;c=(96,211,145) if self.room_id in self.switches else (229,73,90)
                    ren.box(p.x,p.y,p.z,1.5,.22,1.5,c)
                p=r.checkpoint
                ren.box(p.x,p.y,p.z,.12,2.7,.12,(221,215,193))
                ren.box(p.x+.5,p.y+1.8,p.z,1,.7,.05,(109,231,177) if self.room_id in self.checkpoints else (79,157,247))
                if r.cap:
                    kind,p=r.cap
                    ren.box(p.x,p.y+wave(t*80)*.2,p.z,.85,.3,.75,{'wing':(227,70,81),'metal':(166,185,200),'vanish':(116,147,238)}[kind])
                ren.box(7,0,-15,1.7,.8,1.7,(50,64,84))
                ren.box(7,.7,-15,.9,1.1,.9,(65,82,109))
                if r.boss is not None and self.boss_hp[self.room_id]>0:
                    p=self.boss_position()
                    ren.box(p.x,0,p.z,2.5,2.2,2.2,(114,142,70))
                    ren.box(p.x,2.2,p.z,1.5,.7,1.4,(205,164,93))
                    ren.box(p.x-.45,2.35,p.z-.74,.25,.25,.1,(244,71,64))
                    ren.box(p.x+.45,2.35,p.z-.74,.25,.25,.1,(244,71,64))
            normal_flush()
        renderer.flush=flush_expansion
        try:super().draw_world()
        finally:renderer.flush=normal_flush
        if self.mode=='play' and not self.map:
            if self.room_id>=8:
                n=sum((self.room_id,i) in self.red_coins for i in range(8))
                self.text('RED %d/8   COURSE %d/2'%(n,sum((self.room_id,i) in self.stars for i in range(2))),20,83,(255,145,145),font=self.small)
                if self.room.boss is not None and self.boss_hp[self.room_id]>0:self.text('KEEPER  '+'O '*self.boss_hp[self.room_id],W/2,78,(255,159,100),center=True)
            if self.cap_time>0:self.text('%s CAP  %02ds'%(self.cap_kind.upper(),self.cap_time),20,110,(141,211,255),font=self.small)
            if self.cannon:self.text('LAUNCH POWER %.0f  |  E TO FIRE'%self.cannon_power,W/2,H-210,(255,213,111),center=True)
    def draw_directory(self):
        self.overlay();self.text('CASTLE DIRECTORY',W/2,54,font=self.big,center=True)
        self.text('PAGE %d / 4   -   LEFT / RIGHT to browse'% (self.map_page+1),W/2,119,(160,197,247),center=True)
        for row,rid in enumerate(range(self.map_page*8,min(32,self.map_page*8+8))):
            r=self.rooms[rid];y=165+row*35
            color=(255,217,119) if rid==self.room_id else (231,232,239) if rid in self.visited else (137,145,168)
            name=('> ' if rid==self.room_id else '  ')+r.name
            self.text(name,100,y,color,font=self.small)
            found=sum((rid,i) in self.stars for i in range(len(r.stars)))
            if rid>=8:found+=int(('red',rid) in self.stars)
            total=len(r.stars)+(1 if rid>=8 else 0)
            self.text('%d / %d'%(found,total),790,y,color,font=self.small)
        self.text('Lobby > East wing | Garden > Lower wing | Red Hall > Upper wing',W/2,472,font=self.small,center=True)
        self.text('Each wing links forward and backward. Every course returns to Lobby.',W/2,499,font=self.small,center=True)
        self.text('Yellow-coin bonus: %s   |   TAB closes'%('FOUND' if ('coins',0) in self.stars else '%d / 30'%min(30,len(self.coins))),W/2,531,font=self.small,center=True)
    def events(self):
        # Map pagination consumes only arrow events while exploration is paused.
        if self.map:
            deferred=[]
            for event in pygame.event.get():
                if event.type==pygame.KEYDOWN and event.key in (pygame.K_LEFT,pygame.K_RIGHT):
                    self.map_page=(self.map_page+(1 if event.key==pygame.K_RIGHT else -1))%4
                else:deferred.append(event)
            for event in deferred:pygame.event.post(event)
        super().events()

if __name__=='__main__':
    Game().run()
