"""Generate synthetic transparent QA shapes. Contains no third-party character art."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import tempfile

from PIL import Image, ImageDraw

project = Path(__file__).resolve().parents[2]
importer = runpy.run_path(str(project / 'scripts/import-naiwa-assets.py'))


def create(output):
    with tempfile.TemporaryDirectory(prefix='pet-synthetic-source-') as temporary:
        source = Path(temporary)
        def png(name, color, size=(420, 560), offset=0):
            image = Image.new('RGBA', size)
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((size[0]*.25, size[1]*.28+offset, size[0]*.78, size[1]*.96), radius=25, fill=color)
            path = source / name; path.parent.mkdir(parents=True, exist_ok=True); image.save(path)
            return hashlib.sha256(path.read_bytes()).hexdigest()
        clips = {}
        for name, count, fps in [('idle', 28, 1000000000/85000000), ('greet',1,12), ('ponder',1,12), ('focused',1,12), ('curious',1,12), ('worried',1,12), ('sleepy',1,12), ('smile',1,12), ('surprised_in',14,18), ('surprised',95,30), ('surprised_out',75,30)]:
            frames = [{'file':f'{i:04}.png','sha256':png(f'{name}/{i:04}.png',(40+(i%5)*10,100,190,255),offset=i%5)} for i in range(count)]
            (source / name / 'manifest.json').write_text(json.dumps({'canvas':{'width':420,'height':560},'groundY':540,'fps':fps,'frameCount':count,'loop':name in ['idle','surprised'],'frames':frames}))
            clips[name]={'manifest':f'{name}/manifest.json'}
        icon = png('icon.png',(40,100,190,255),(256,256))
        notice = source / 'NOTICE.txt'; notice.write_text('SYNTHETIC QA FIXTURE. No NaiWa art is included. Do not distribute as the new character.')
        selection={'upstream_ref':importer['PIN'],'repository':'https://github.com/SbongeBobybl/NaiWaChatPet','rights':{'status':'verified','basis':'Generated synthetic QA shapes; no upstream art'},'canvas':{'width':420,'height':560},'ground_y':540,'clips':clips,'states':{'starting':'greet','idle':'idle','thinking':'ponder','replying':'focused','approval':'curious','error':'worried','sleeping':'sleepy'},'actions':[{'id':'greet','title':'打招呼','clips':['greet'],'hold_ms':800},{'id':'smile','title':'微笑','clips':['smile'],'hold_ms':800},{'id':'surprised','title':'惊讶','clips':['surprised_in','surprised','surprised_out']}],'icon':{'source':'icon.png','sha256':icon},'declarations':[{'source':'NOTICE.txt','sha256':hashlib.sha256(notice.read_bytes()).hexdigest()}]}
        pack=importer['import_asset_pack'](source,selection,output,source_ref=importer['PIN'])
        pack['qa_fixture']=True
        (output / 'asset-pack.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    create(parser.parse_args().output)
