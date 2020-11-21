from django.shortcuts import render
from django.http import HttpResponse
import pandas as pd
import numpy as np
from lxml import etree as et
import json
import requests

def index(request):
    return render(request,'pharmasug20app/index.html')

def GetVars(request):
    # Define namespaces
    nsdefault='http://www.cdisc.org/ns/odm/v1.3'
    nsdefine='http://www.cdisc.org/ns/def/v2.0'
    nsxlink='http://www.w3.org/1999/xlink'
    ns = {'odm':nsdefault,'def':nsdefine,'xlink':nsxlink}

    # Get VS variables from Define
    parser = et.XMLParser(remove_comments=True,remove_blank_text=True,remove_pis=False)
    #tree = et.parse('/var/www/html/define2.xml',parser)
    tree = et.parse('pharmasug20app/define2.xml',parser)
    root = tree.getroot()

    dflist1 = []
    VS = root.find('.//odm:ItemGroupDef[@Name="VS"]',ns)

    for itemref in VS.iterfind('odm:ItemRef',ns):
        ItemOID = itemref.get('ItemOID')
        itemdef = root.find('.//odm:ItemDef[@OID="'+ItemOID+'"]',ns)
        varname = itemdef.get('Name').upper()
        label = itemdef.find('.//odm:TranslatedText',ns).text
        datatype = itemdef.get('DataType')
        codelistref = itemdef.find('.//odm:CodeListRef',ns)

        if codelistref is not None:
            codelistoid = codelistref.get('CodeListOID')
            codelist = root.find('.//odm:CodeList[@OID="'+codelistoid+'"]',ns)
            definecodelistname = codelist.get('Name')
            codelistalias = codelist.find('odm:Alias',ns)
            code = codelistalias.get('Name') if codelistalias is not None else ''

        else:
            definecodelistname = ''
            with open('../VS_'+varname+'.txt','r') as f:
                #req = requests.get("http://library.cdisc.org/api/mdr/sdtmig/3-2/datasets/VS/variables/"+varname,auth=('prahs001',';;fallWORN23;;'),headers={'Accept':'application/json'})
                #jl = json.loads(req.text)
                jl = json.load(f)
                if 'codelist' in jl['_links']:
                    href = jl['_links']['codelist'][0]['href']
                    code = href.split(sep='/')[-1]

                else:
                    code = ''
                    
        dflist1.append({'itemoid':ItemOID,'var':varname,'label':label,'datatype':datatype,'DefCLName':definecodelistname,'code':code})

    df = pd.DataFrame(dflist1)
    return HttpResponse(df.to_json(orient='records'),content_type='application/json')

def GetCodes(request):
    CLCode = request.GET['CLCode']
    ItemOID = request.GET['ItemOID']
    VarName = request.GET['varName']
    VarDataType = request.GET['varType']
    DefineCLName = request.GET['DefineCLName']

    # Get Standard Terminology for the requested codelist
    if CLCode:
        dflist1 = []
        with open('../sdtmct-2019-09-27.txt','r') as file:
            jl = json.loads(file.read())
            for x in jl['codelists']:
                if x['conceptId'] == CLCode:
                    StdCLName = x['name']
                    CLExt = x['extensible']
                    for y in x['terms']:
                        dflist1.append({'sv':y['submissionValue'],'pt':y['preferredTerm'],'termcode':y['conceptId']})
                    break
        
        df1 = pd.DataFrame(dflist1)

    # Get terminology in study
    if DefineCLName:
        dflist2 = []
        # Define namespaces
        nsdefault='http://www.cdisc.org/ns/odm/v1.3'
        nsdefine='http://www.cdisc.org/ns/def/v2.0'
        nsxlink='http://www.w3.org/1999/xlink'
        ns = {'odm':nsdefault,'def':nsdefine,'xlink':nsxlink}

        parser = et.XMLParser(remove_comments=True,remove_blank_text=True,remove_pis=False)
        tree = et.parse('pharmasug20app/define2.xml',parser)
        root = tree.getroot()

        DefCodeList = root.find('.//odm:CodeList[@Name="'+DefineCLName+'"]',ns)
        for cli in DefCodeList.iterfind('odm:CodeListItem',ns):
            tt = cli.find('odm:Decode/odm:TranslatedText',ns)
            dflist2.append({'sv':cli.get('CodedValue'),'decode':tt.text,'state':True})

        df2 = pd.DataFrame(dflist2)

    if CLCode and DefineCLName:
        df = pd.merge(df1,df2,how='outer',on='sv')
        print (df)  
        df['Decode'] = pd.Series(row['pt'] if not pd.isnull(row['pt']) else row['decode'] for i,row in df.iterrows())
        df['Extensible'] = CLExt
        df['CLName'] = DefineCLName
        df['CLCode'] = CLCode
        df.drop(['pt','decode'],axis=1,inplace=True)

    elif CLCode:
        df = df1
        df.rename({'pt':'Decode'},axis=1,inplace=True)
        df['Extensible'] = CLExt
        df['CLName'] = StdCLName
        df['CLCode'] = CLCode

    elif DefineCLName:
        pass

    else:
        pass

    df['ItemOID'] = ItemOID
    return HttpResponse(df.to_json(orient='records'),content_type='application/json')

def RefreshDefine(request):
    SelCodes = json.loads(request.GET['selections'])
    CLName = request.GET['CLName']

    ItemOID = SelCodes[0]['ItemOID']
    CLCode = SelCodes[0]['CLCode']

    nsdefault='http://www.cdisc.org/ns/odm/v1.3'
    nsdefine='http://www.cdisc.org/ns/def/v2.0'
    nsxlink='http://www.w3.org/1999/xlink'
    ns = {'odm':nsdefault,'def':nsdefine,'xlink':nsxlink}

    # Get VS variables from Define
    parser = et.XMLParser(remove_comments=True,remove_blank_text=True,remove_pis=False)
    tree = et.parse('pharmasug20app/define2.xml',parser)
    root = tree.getroot()

    # Determine if a codelist is already present for this variable by determining if the variable has a CodeListRef element
    ItemDef = root.find('.//odm:ItemDef[@OID="'+ItemOID+'"]',ns)
    CodeListRef = ItemDef.find('odm:CodeListRef',ns)
    # if no CodeListRef element exists, add one
    if CodeListRef is None:
        CodeListRefE = et.SubElement(ItemDef,'CodeListRef',CodeListOID='CL.VS.'+ItemDef.get('Name'))
    # Otherwise find the current CodeList and delete it
    else:
        CodeListOID = CodeListRef.get('CodeListOID')
        CodeList = root.find('.//odm:CodeList[@OID="'+CodeListOID+'"]',ns)
        parent = CodeList.getparent()
        parent.remove(CodeList)
    # Now add the new codelist
    NewCodeListE = et.Element('CodeList',OID='CL.VS.'+ItemDef.get('Name'),DataType=ItemDef.get('DataType'),Name=CLName)
    for x in SelCodes:
        CodeListItemE = et.SubElement(NewCodeListE,'CodeListItem',CodedValue=x['sv'])
        Decode = et.SubElement(CodeListItemE,'Decode')
        TT = et.SubElement(Decode,'TranslatedText',lang="en")
        TT.text = x['Decode']

        if x['termcode']:
            AliasE = et.SubElement(CodeListItemE,'Alias',Name=x['termcode'],Context='nci:ExtCodeID')
        else:
            CodeListItemE.attrib[et.QName(nsdefine,'ExtendedValue')]='Yes'

    CLAliasE = et.SubElement(NewCodeListE,'Alias',Name=CLCode,Context='nci:ExtCodeID')

    lastitemdef = root.find('.//odm:ItemDef[last()]',ns)
    lastitemdef.addnext(NewCodeListE)

    tree.write('pharmasug20app/define2.xml',pretty_print=True,xml_declaration=True)
    return render(request,'pharmasug20app/index.html')