import unreal
ROOT='/Game/Earth/EarthCommand/Engineering/Production/Materials'
path=ROOT+'/M_ODY_ProductionGlass'
eal=unreal.EditorAssetLibrary
if not eal.does_asset_exist(path):
    m=unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_ODY_ProductionGlass',ROOT,unreal.Material,unreal.MaterialFactoryNew())
    m.set_editor_property('blend_mode',unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property('two_sided',True)
    m.set_editor_property('translucency_lighting_mode',unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    mel=unreal.MaterialEditingLibrary
    color=mel.create_material_expression(m,unreal.MaterialExpressionConstant3Vector)
    color.set_editor_property('constant',unreal.LinearColor(0.12,0.18,0.19,1))
    mel.connect_material_property(color,'',unreal.MaterialProperty.MP_BASE_COLOR)
    for value,prop in [(0.0,unreal.MaterialProperty.MP_METALLIC),(0.055,unreal.MaterialProperty.MP_ROUGHNESS),(0.5,unreal.MaterialProperty.MP_SPECULAR),(0.08,unreal.MaterialProperty.MP_OPACITY),(1.46,unreal.MaterialProperty.MP_REFRACTION)]:
        c=mel.create_material_expression(m,unreal.MaterialExpressionConstant)
        c.set_editor_property('r',value)
        mel.connect_material_property(c,'',prop)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
print('PRODUCTION_GLASS_READY')
