"""Production PBR materials in Unreal, isolated from verification-map materials."""
import unreal, os, sys

ROOT = '/Game/Earth/EarthCommand/Engineering/Production'
HERE = os.path.dirname(__file__)
eal=unreal.EditorAssetLibrary
at=unreal.AssetToolsHelpers.get_asset_tools()
mel=unreal.MaterialEditingLibrary

textures={}
for name in ['T_ODY_MicroRoughness','T_ODY_BrushedNormal','T_ODY_EngineeringDisplay','T_ODY_ServiceDecal']:
    path=ROOT+'/Textures/'+name
    if not eal.does_asset_exist(path):
        t=unreal.AssetImportTask()
        for k,v in {'filename':os.path.join(HERE,'surface_textures',name+'.png'),'destination_path':ROOT+'/Textures','automated':True,'save':True,'replace_existing':False}.items():t.set_editor_property(k,v)
        at.import_asset_tasks([t])
    tex=unreal.load_asset(path)
    assert tex, path
    if name in ['T_ODY_MicroRoughness','T_ODY_BrushedNormal']:tex.set_editor_property('srgb',False)
    if name=='T_ODY_BrushedNormal':tex.set_editor_property('compression_settings',unreal.TextureCompressionSettings.TC_NORMALMAP)
    eal.save_loaded_asset(tex)
    textures[name]=tex

def expr(m,cls,**props):
    e=mel.create_material_expression(m,cls)
    for k,v in props.items():e.set_editor_property(k,v)
    return e
def scalar(m,name,v):return expr(m,unreal.MaterialExpressionScalarParameter,parameter_name=name,default_value=float(v))
def vector(m,name,v):return expr(m,unreal.MaterialExpressionVectorParameter,parameter_name=name,default_value=unreal.LinearColor(*v,1))
def link(a,b,inp='A',out=''):
    pins=list(mel.get_material_expression_input_names(b))
    if inp=='Input' and inp not in pins:inp=pins[0]
    assert mel.connect_material_expressions(a,out,b,inp),(b.get_class().get_name(),inp,pins,out)
def output(a,p,out=''):assert mel.connect_material_property(a,out,p)
def product(m,a,b):
    x=expr(m,unreal.MaterialExpressionMultiply);link(a,x);link(b,x,'B');return x
def finish(m):
    mel.recompile_material(m)
    eal.set_metadata_tag(m,'OdysseyProductionGraphReady','3' if m.get_name()=='M_ODY_ConsoleHero' else '1')
    eal.save_loaded_asset(m)
def material(name):
    path=ROOT+'/Materials/'+name
    if eal.does_asset_exist(path):
        m=unreal.load_asset(path)
        if eal.get_metadata_tag(m,'OdysseyProductionGraphReady')!=('3' if name=='M_ODY_ConsoleHero' else '1'):
            mel.delete_all_material_expressions(m)
            return m,True
        return m,False
    return at.create_asset(name,ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew()),True

master,new=material('M_ODY_ProductionSurface')
if new:
    base=vector(master,'BaseColor',(0.5,0.5,0.5))
    metal=scalar(master,'Metallic',0)
    rough=scalar(master,'Roughness',0.5)
    uv=expr(master,unreal.MaterialExpressionTextureCoordinate,u_tiling=6.0,v_tiling=6.0)
    noise=expr(master,unreal.MaterialExpressionTextureSample,texture=textures['T_ODY_MicroRoughness'],sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    link(uv,noise,'UVs')
    remap=expr(master,unreal.MaterialExpressionMultiply,const_b=0.2);link(noise,remap,out='R')
    offset=expr(master,unreal.MaterialExpressionAdd,const_b=0.9);link(remap,offset)
    normal=expr(master,unreal.MaterialExpressionTextureSample,texture=textures['T_ODY_BrushedNormal'],sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    link(uv,normal,'UVs')
    output(base,unreal.MaterialProperty.MP_BASE_COLOR)
    output(metal,unreal.MaterialProperty.MP_METALLIC)
    output(product(master,rough,offset),unreal.MaterialProperty.MP_ROUGHNESS)
    output(normal,unreal.MaterialProperty.MP_NORMAL)
    ec=vector(master,'EmissiveColor',(0,0,0));strength=scalar(master,'EmissiveStrength',0);scale=scalar(master,'EmissiveScale',1)
    output(product(master,product(master,ec,strength),scale),unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(master)

sys.path.insert(0,os.path.join(unreal.Paths.project_dir(),'ArtSource/OdysseyAssetPack/Source'))
from od_gltf import MATERIALS,srgb_to_linear
for name,(color,metal,rough,ec,estr,alpha) in MATERIALS.items():
    if globals().get('ONLY_HERO',False):continue
    if alpha<1:continue
    path=ROOT+'/Materials/MI_Prod_'+name.removeprefix('OD_MAT_')
    mi=unreal.load_asset(path) if eal.does_asset_exist(path) else at.create_asset(path.rsplit('/',1)[1],ROOT+'/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi,master)
    mel.set_material_instance_vector_parameter_value(mi,'BaseColor',unreal.LinearColor(*srgb_to_linear(color),1))
    mel.set_material_instance_scalar_parameter_value(mi,'Metallic',metal)
    mel.set_material_instance_scalar_parameter_value(mi,'Roughness',rough)
    # Status accents remain restrained; amber is physical hazard paint.
    if 'IonBlue' in name:estr=20
    if 'Amber' in name:estr=0
    if 'EmergencyRed' in name:estr=0.25
    if 'Diffuser' in name:estr=400
    if ec:mel.set_material_instance_vector_parameter_value(mi,'EmissiveColor',unreal.LinearColor(*srgb_to_linear(ec),1))
    mel.set_material_instance_scalar_parameter_value(mi,'EmissiveStrength',estr)
    mel.set_material_instance_scalar_parameter_value(mi,'EmissiveScale',1)
    eal.save_loaded_asset(mi)

screen,new=material('M_ODY_ProductionDisplay')
if new:
    tex=expr(screen,unreal.MaterialExpressionTextureSample,texture=textures['T_ODY_EngineeringDisplay'])
    output(tex,unreal.MaterialProperty.MP_BASE_COLOR)
    output(scalar(screen,'Roughness',0.14),unreal.MaterialProperty.MP_ROUGHNESS)
    output(product(screen,tex,scalar(screen,'EmissiveScale',40)),unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(screen)

console,new=material('M_ODY_ConsoleHero')
if new:
    cp=ROOT+'/ConsoleHero/OD_ENG_PowerConsole_PNG_texture_'
    base=expr(console,unreal.MaterialExpressionTextureSample,texture=unreal.load_asset(cp+'0'))
    orm=expr(console,unreal.MaterialExpressionTextureSample,texture=unreal.load_asset(cp+'1'),sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    paint_gain=product(console,base,scalar(console,'PaintAlbedoGain',1.6))
    paint=expr(console,unreal.MaterialExpressionClamp,min_default=0.0,max_default=0.82);link(paint_gain,paint,'Input')
    output(paint,unreal.MaterialProperty.MP_BASE_COLOR)
    output(orm,unreal.MaterialProperty.MP_ROUGHNESS,'G')
    # The source atlas marks the painted shell as metal. Painted metal is a dielectric surface.
    output(scalar(console,'PaintMetallic',0.0),unreal.MaterialProperty.MP_METALLIC)
    # Cyan-only mask lights screen graphics and status strips; neutral paint emits nothing.
    gb=expr(console,unreal.MaterialExpressionMin);link(base,gb,'A','G');link(base,gb,'B','B')
    red=expr(console,unreal.MaterialExpressionMultiply,const_b=1.8);link(base,red,'A','R')
    sub=expr(console,unreal.MaterialExpressionSubtract);link(gb,sub,'A');link(red,sub,'B')
    threshold=expr(console,unreal.MaterialExpressionAdd,const_b=-0.01);link(sub,threshold)
    gain=expr(console,unreal.MaterialExpressionMultiply,const_b=16.0);link(threshold,gain)
    clamp=expr(console,unreal.MaterialExpressionClamp,min_default=0.0,max_default=1.0);link(gain,clamp,'Input')
    output(product(console,product(console,base,clamp),scalar(console,'EmissiveScale',400)),unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(console)
decal,new=material('M_ODY_ServiceDecal')
if new:
    decal.set_editor_property('material_domain',unreal.MaterialDomain.MD_DEFERRED_DECAL)
    decal.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    tex=expr(decal,unreal.MaterialExpressionTextureSample,texture=textures['T_ODY_ServiceDecal'])
    output(tex,unreal.MaterialProperty.MP_BASE_COLOR)
    output(tex,unreal.MaterialProperty.MP_OPACITY,'A')
    output(scalar(decal,'Roughness',0.65),unreal.MaterialProperty.MP_ROUGHNESS)
    finish(decal)
print('PRODUCTION_MATERIALS_READY')
