#!/usr/bin/env python3
"""Render REPORT.md as four main pages and one references page."""
import argparse,html,re
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]

def inline(text):
    text=html.escape(text)
    text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',lambda m:'<link href="'+m[2]+'" color="#184c79">'+m[1]+'</link>',text)
    text=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'`([^`]+)`',r'<font name="Courier" size="8.6">\1</font>',text)
    return text

def build(source,dest):
    styles={
      'body':ParagraphStyle('body',fontName='Times-Roman',fontSize=10.5,leading=13.0,spaceAfter=6.5),
      'title':ParagraphStyle('title',fontName='Times-Bold',fontSize=18,leading=20.5,spaceAfter=10),
      'h2':ParagraphStyle('h2',fontName='Times-Bold',fontSize=12,leading=14,spaceBefore=7,spaceAfter=5,keepWithNext=True),
      'h3':ParagraphStyle('h3',fontName='Times-Bold',fontSize=10.8,leading=13,spaceBefore=5,spaceAfter=4,keepWithNext=True),
      'cell':ParagraphStyle('cell',fontName='Times-Roman',fontSize=8.6,leading=10.5,spaceAfter=0),
    }
    doc=SimpleDocTemplate(str(dest),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=38,bottomMargin=38,
        title='Cross-Candidate Verification for Scientific Software Repair',author='SelfVerify research project')
    content=source.read_text()
    if '<!-- PAGEBREAK -->' not in content:
        for heading in ('## 2. How the method handles one task','## 4. What was solved?','## 5. What do these results tell us?','## References'):
            if content.count(heading)!=1:raise ValueError('Missing or repeated report heading: '+heading)
            content=content.replace(heading,'<!-- PAGEBREAK -->\n\n'+heading,1)
    sections=content.split('<!-- PAGEBREAK -->')
    if len(sections)!=5:raise ValueError('Expected four main sections and references')
    story=[]
    for page,section in enumerate(sections):
        if page:story.append(PageBreak())
        lines=section.strip().splitlines();i=0
        while i<len(lines):
            line=lines[i].strip()
            if not line:i+=1;continue
            if line.startswith('|'):
                rows=[]
                while i<len(lines) and lines[i].strip().startswith('|'):
                    row=[c.strip() for c in lines[i].strip().strip('|').split('|')]
                    if not all(re.fullmatch(r'[-: ]+',c) for c in row):rows.append(row)
                    i+=1
                columns=len(rows[0])
                if columns==4:widths=[105]+[(doc.width-105)/3]*3
                elif columns==3:widths=[105]+[(doc.width-105)/2]*2
                elif columns==5:widths=[65]+[(doc.width-65)/4]*4
                elif columns==2:widths=[doc.width-120,120]
                else:widths=[doc.width/columns]*columns
                table=Table([[Paragraph(inline(c),styles['cell']) for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
                table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf0f5')),
                  ('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#708090')),('LINEBELOW',(0,-1),(-1,-1),.4,colors.HexColor('#708090')),
                  ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),
                  ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
                story.extend([table,Spacer(1,7)]);continue
            style='body'
            if line.startswith('# '):style='title';line=line[2:]
            elif line.startswith('## '):style='h2';line=line[3:]
            elif line.startswith('### '):style='h3';line=line[4:]
            else:
                while i+1<len(lines) and lines[i+1].strip() and not lines[i+1].startswith(('#','|')):
                    i+=1;line+=' '+lines[i].strip()
            story.append(Paragraph(inline(line),styles[style]));i+=1
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('Times-Roman',9);canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawString(42,23,'Cross-Candidate Verification | Nine-task study')
        canvas.drawRightString(A4[0]-42,23,str(doc.page));canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    pdf=PdfReader(dest)
    if len(pdf.pages)!=5 or 'References' not in pdf.pages[4].extract_text()[:250]:
        raise RuntimeError(f'Layout exceeds budget or references misplaced: {len(pdf.pages)} pages')
    for n,p in enumerate(pdf.pages):
        if not p.extract_text().strip():raise RuntimeError('Empty page')
    print(f'{dest}: 4 main pages + 1 references page')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,default=ROOT/'REPORT.md');ap.add_argument('--out',type=Path,default=ROOT/'REPORT.pdf');a=ap.parse_args();build(a.source,a.out)
