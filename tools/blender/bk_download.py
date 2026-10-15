r"""Скачать бесплатные модели BlenderKit в D:\pol-ai\bk_assets (нужен вход в аддон BlenderKit).
Запуск: D:\pol-ai\blender\blender.exe -b -P tools/blender/bk_download.py -- <assetBaseId> ...
Ключ берётся из настроек аддона и никуда не выводится."""
import bpy,json,urllib.request,urllib.parse,os,uuid,time,sys
ids=sys.argv[sys.argv.index('--')+1:]
key=bpy.context.preferences.addons['blenderkit'].preferences.api_key
out='D:/pol-ai/bk_assets'; os.makedirs(out,exist_ok=True)
H={'Authorization':'Bearer '+key,'User-Agent':'pol-za-minutu'}
su=str(uuid.uuid4())
for aid in ids:
    try:
        u='https://www.blenderkit.com/api/v1/search/?query='+urllib.parse.quote('asset_base_id:'+aid)
        r=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=30))['results'][0]
        f=[x for x in r['files'] if x['fileType']=='blend'][0]
        j=json.load(urllib.request.urlopen(urllib.request.Request(f['downloadUrl']+'?scene_uuid='+su,headers=H),timeout=60))
        dst=f"{out}/{aid}.blend"
        open(dst,'wb').write(urllib.request.urlopen(urllib.request.Request(j['filePath'],headers={'User-Agent':'Mozilla/5.0'}),timeout=300).read())
        print('OK',aid,r['name'],os.path.getsize(dst)//1024,'KB',flush=True)
    except Exception as e:
        print('FAIL',aid,type(e).__name__,str(e)[:120],flush=True)
    time.sleep(2)
