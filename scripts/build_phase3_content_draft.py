#!/usr/bin/env python3
"""Create bounded Phase 3C AI-draft learner content from frozen reviewed senses.

Text is authored as an AI draft with unknown model identity; it is deliberately
not semantic-review status and must be externally reviewed before any runtime use.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; INPUT=ROOT/'data/phase3/content-150-input.json'; OUT=ROOT/'data/phase3/learner-content-150-draft.json'; REVIEW=ROOT/'data/phase3/learner-content-150-review.jsonl'
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
GLOSS={}
for line in '''prêt|ADJ\t准备好的\nsuivant|ADJ\t下一个的\nfamilial|ADJ\t家庭的\nsoudain|ADV\t突然地\navant|ADV\t在前；以前\nforcément|ADV\t必然地\nrésultat|NOM\t结果\nchoisir|VER\t选择\nconcerner|VER\t涉及；关系到\néviter|VER\t避免\ninternational|ADJ\t国际的\ndivers|ADJ\t各种各样的\nétrange|ADJ\t奇怪的\nfinalement|ADV\t最后；终于\ntranquillement|ADV\t平静地\nsurveiller|VER\t监视；照看\nresponsable|ADJ\t负责的\nadministratif|ADJ\t行政的\ntechnique|ADJ\t技术的\nexclamer|VER\t惊呼\ntouristique|ADJ\t旅游的\nartistique|ADJ\t艺术的\nrassurer|VER\t使安心\nnombreux|ADJ\t众多的\npersonnel|ADJ\t个人的\nlittéraire|ADJ\t文学的\nintellectuel|ADJ\t智力的\nmal|ADV\t不好地\nnotamment|ADV\t尤其；特别是\ncomplètement|ADV\t完全地\nessentiellement|ADV\t本质上；主要地\nsoir|NOM\t傍晚\nenquête|NOM\t调查\nsorte|NOM\t种类\nchercheur|NOM\t研究人员\ndevenir|VER\t变成\nhésiter|VER\t犹豫\nempêcher|VER\t阻止\nsouligner|VER\t在下方划线\nimportant|ADJ\t重要的\nimmense|ADJ\t巨大的\nsombre|ADJ\t昏暗的\nissu|ADJ\t源自……的\nautour|ADV\t在周围\nactuellement|ADV\t目前；现在\nvoire|ADV\t甚至\nnuit|NOM\t夜晚\nmoitié|NOM\t一半\npublic|NOM\t公众；观众\nexpliquer|VER\t解释\nconstater|VER\t确认；发现\nattirer|VER\t吸引；拉向\ncraindre|VER\t害怕；担心\ndifférent|ADJ\t不同的\nquotidien|ADJ\t每天的\nrécent|ADJ\t最近的\nfameux|ADJ\t著名的\nparfois|ADV\t有时\nmalheureusement|ADV\t不幸地\nfort|ADV\t强烈地\nmoment|NOM\t时刻\nprésident|NOM\t主席；总统\nexpérience|NOM\t经验\nsembler|VER\t似乎；显得\ntaire|VER\t不说；隐瞒\nimporter|VER\t进口\npossible|ADJ\t可能的\naméricain|ADJ\t美国的\nunique|ADJ\t唯一的\négalement|ADV\t也；同样地\ndehors|ADV\t在外面\nautrefois|ADV\t从前\nmatin|NOM\t早晨\nfort|ADJ\t强壮的\nlourd|ADJ\t沉重的\nphysique|ADJ\t物质的；物理的\nessentiel|ADJ\t必不可少的\nau-dessus|ADV\t在上方\ndebout|ADV\t站着\nmonsieur|NOM\t先生\nor|NOM\t黄金\nétat|NOM\t状态\nréseau|NOM\t网络\ndonner|VER\t赠送；给\nplacer|VER\t放置\nlier|VER\t系；连接\nlutter|VER\t同……斗争\ngros|ADJ\t大的；粗的\nmalheureux|ADJ\t不幸的\nprofond|ADJ\t深的\ndoucement|ADV\t轻柔地\nabsolument|ADV\t完全地\ntravail|NOM\t工作；职业\nauteur|NOM\t作者\npouvoir|NOM\t力量；效力\ndébat|NOM\t讨论；辩论\naimer|VER\t喜欢；觉得愉快\nentraîner|VER\t训练\nvaloir|VER\t值；具有价值\ndisposer|VER\t拥有；可使用\nblanc|ADJ\t白色的\nactif|ADJ\t积极的；活跃的\nprivé|ADJ\t私人的\nheureusement|ADV\t幸运地\nville|NOM\t城市\nvaleur|NOM\t价值；重要性\ncommissaire|NOM\t警察局长\nreprésentation|NOM\t表现；呈现\ndemander|VER\t请求；要求\nremplir|VER\t装满\néchapper|VER\t逃脱\nétendre|VER\t展开；扩展\nplein|ADJ\t满的\npopulaire|ADJ\t受欢迎的\nouvert|ADJ\t打开的\nami|NOM\t朋友\nsujet|NOM\t主题；题目\nesprit|NOM\t思想；心智\nlien|NOM\t联系；纽带\narriver|VER\t到达\nappartenir|VER\t属于\nestimer|VER\t估计；重视\nsoutenir|VER\t支持；鼓励\nheureux|ADJ\t幸福的\ncapable|ADJ\t能够的\nfaible|ADJ\t虚弱的\nfille|NOM\t女孩\nsentiment|NOM\t感情\nsystème|NOM\t系统\ncapacité|NOM\t能力\npenser|VER\t认为\nabandonner|VER\t放弃；离开\ntendre|VER\t拉紧；伸展\nappliquer|VER\t应用；使用\nnoir|ADJ\t黑色的\nvif|ADJ\t有活力的\npère|NOM\t父亲\npapier|NOM\t纸\nligne|NOM\t线\nregarder|VER\t看\nconsacrer|VER\t用于；奉献给\ncharger|VER\t装载\nsimple|ADJ\t简单的\nprécieux|ADJ\t珍贵的\nmain|NOM\t手\ngarde|NOM\t保护；看守\naction|NOM\t作用；行动\nrester|VER\t保持；停留\nengager|VER\t抵押\naffirmer|VER\t断言；肯定'''.splitlines():
    key,value=line.split('\t');GLOSS[key]=value
SPECIAL={
'personne|NOM':('人；个人','C’est une personne très calme.','这是一个很平静的人。'),
'pouvoir|NOM':('力量；效力','Ce médicament a un grand pouvoir.','这种药效力很强。'),
'père|NOM':('父亲','Son père arrive ce soir.','他的父亲今晚到。'),
'or|NOM':('黄金','Cette bague est en or.','这枚戒指是金的。'),
'travail|NOM':('工作；职业','Elle cherche du travail.','她在找工作。'),
'aimer|VER':('喜欢；觉得愉快','J’aime cette musique.','我喜欢这段音乐。'),
'lutter|VER':('同……斗争','Nous luttons contre la faim.','我们与饥饿作斗争。'),
'importer|VER':('进口','Le pays importe du café.','这个国家进口咖啡。'),
'placer|VER':('放置','Place le livre sur la table.','把书放在桌上。'),
'lier|VER':('系；连接','Il lie les deux cordes.','他把两根绳子系在一起。'),
'souligner|VER':('在下方划线','Souligne ce mot.','在这个词下面画线。'),
'remplir|VER':('装满','Remplis le verre d’eau.','把杯子装满水。'),
'échapper|VER':('逃脱','Le chat échappe au chien.','猫逃过了狗。'),
'étendre|VER':('展开；扩展','Elle étend la nappe.','她把桌布铺开。'),
'engager|VER':('抵押','Il engage sa montre.','他抵押了手表。'),
}
def article(lemma):return 'une' if lemma.endswith(('e','té','ion')) else 'un'
def example(row,gloss):
    if row['stable_lexeme_key'] in SPECIAL:return SPECIAL[row['stable_lexeme_key']][1:]
    lemma=row['lemma'];pos=row['pos']
    if pos=='VER':return (f'Nous allons {lemma}.',f'我们将{gloss.split("；")[0]}。')
    if pos=='NOM':return (f'Voici {article(lemma)} {lemma}.',f'这是一个{gloss.split("；")[0]}。')
    if pos=='ADJ':return (f'C’est {lemma}.',f'这是{gloss.split("；")[0]}的。')
    return (f'Il agit {lemma}.',f'他{gloss.split("；")[0]}地行动。')
def build():
    source=json.loads(INPUT.read_text());items=[]
    for row in source['items']:
        gloss=GLOSS.get(row['stable_lexeme_key'])
        if not gloss:raise SystemExit(f'missing gloss: {row["stable_lexeme_key"]}')
        fr,zh=example(row,gloss);items.append({'stable_lexeme_key':row['stable_lexeme_key'],'lemma':row['lemma'],'pos':row['pos'],'cefr':row['cefr'],'entry_id':row['entry_id'],'sense_id':row['sense_id'],'definition_fr':row['definition_fr'],'content_authoring_risk_tier':row['content_authoring_risk_tier'],'translation_binding_risk_tier':row['translation_binding_risk_tier'],'gloss_zh_short':SPECIAL.get(row['stable_lexeme_key'],(gloss,))[0],'usage_note_zh':None,'example_fr':fr,'example_zh':zh,'example_source_type':'ai_generated','gloss_source_strategy':'ai_gap_fill','used_candidate_refs':[],'rejected_candidates':[],'content_status':'ai_draft','provenance':{'authoring_surface':'Codex agent','actual_model':'unknown','generation_version':'phase3c-150-ai-draft-v1','input_facts_hash':row['parent_input_hash']}})
    body={'schema_version':1,'scope':'Phase 3C bounded AI-draft learner content; exact French senses are externally reviewed and content remains unreviewed.','input_artifact_hash':source['artifact_hash'],'items':items};body['artifact_hash']=digest(body);return body
def write():
    body=build();OUT.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n');lines=[]
    for x in body['items']:
        lines.append(canonical({k:x[k] for k in ('stable_lexeme_key','lemma','pos','cefr','content_authoring_risk_tier','translation_binding_risk_tier','entry_id','sense_id','definition_fr','gloss_zh_short','usage_note_zh','example_fr','example_zh','gloss_source_strategy','example_source_type')})+'\n')
    REVIEW.write_text(''.join(lines));return body
if __name__=='__main__':print(json.dumps({'items':len(write()['items'])}))
