import sys
from psd_tools import PSDImage
psd=PSDImage.open(sys.argv[1])
print(psd.size)
def walk(g,d=0):
    for l in g:
        extra=''
        if l.kind=='type':
            rs=l.engine_dict['StyleRun']['RunArray'][0]['StyleSheet']['StyleSheetData']
            fs=[f['Name'] for f in l.resource_dict['FontSet']]
            extra=f"{l.text!r} size={rs.get('FontSize')} font={fs[rs.get('Font',0)]} tf={tuple(round(v,3) for v in l.transform)} fx={l.has_effects()}"
        print('  '*d+f"[{l.kind}] id={l.layer_id} {l.name!r} vis={l.visible} bbox={l.bbox} {extra}")
        if l.is_group(): walk(l,d+1)
walk(psd)
