## Script (Python) "navigation_tree_builder"
##parameters=tree_root,navBatchStart=0,showMyUserFolderOnly=None,includeTop=None,showFolderishSiblingsOnly=None,showFolderishChildrenOnly=None,showNonFolderishObject=None,topLevel=None,batchSize=None,showTopicResults=None,rolesSeeUnpublishedContent=None,sortCriteria=None,metaTypesNotToList=None,parentMetaTypesNotToQuery=None
##title=Standard Tree
##
#Stateless Tree Navigation
#(c) Philipp Auersperg phil@bluedynamics.com 10.09.2002

from Products.CMFPlone.StatelessTreeNav import StatelessTreeBuilder
from Products.CMFPlone.StatelessTreeNav import wrap_obj
from Products.CMFCore.utils import getToolByName

# if possible get the options from the portal_properties
props=getToolByName(context,'portal_properties')
if hasattr(props,'navtree_properties'):
    props=props.navtree_properties

# show only the userFolder I am browsing and my own one
if showMyUserFolderOnly is None:
    showMyUserFolderOnly=getattr(props,'showMyUserFolderOnly',  1)

#if set, the top object itself is included in the tree
if includeTop is None:
    includeTop=getattr(props,'includeTop',  1)

#in the hierarchy above the leaf object just folders should be displayed
if showFolderishSiblingsOnly is None:
    showFolderishSiblingsOnly=getattr(props,'showFolderishSiblingsOnly',  1)

if showFolderishChildrenOnly is None:
    #list only folders below the leaf object
    showFolderishChildrenOnly=getattr(props,'showFolderishChildrenOnly',  0)

if showNonFolderishObject is None:
    #if the leaf object is not a folder and showFolderishChildrenOnly the leaf is displayed in any case, but not its siblings
    showNonFolderishObject=getattr(props,'showNonFolderishObject',  0)

if topLevel is None:
    topLevel=getattr(props,'topLevel',  0)

if batchSize is None:
    # how long should one batch be. per definition it stops not before the leaf object is reached
    batchSize=getattr(props,'batchSize',  30)

if showTopicResults is None:
    # show results of topics in the tree
    showTopicResults=getattr(props,'showTopicResults',  1)

if rolesSeeUnpublishedContent is None:
    # these (local) roles can see unpublished 
    rolesSeeUnpublishedContent=getattr(props,'rolesSeeUnpublishedContent',  ['Manager','Reviewer','Owner'])

if metaTypesNotToList is None:
    # there is some VERY weird error with Collectors,
    # so I have to remove from the list
    metaTypesNotToList=getattr(props,'metaTypesNotToList',  ['CMF Collector','CMF Collector Issue','CMF Collector Catalog'])

if parentMetaTypesNotToQuery is None:
    # these types should not be queried for children
    parentMetaTypesNotToQuery=getattr(props,'parentMetaTypesNotToQuery',  [])  

# put in here the meta_types not to be listed
if sortCriteria is None:
    sortCriteria=getattr(props, 'sortCriteria', [('isPrincipiaFolderish','desc'),('Title','asc')])

if not same_type(sortCriteria, []):
    criteria=[]
    for c in sortCriteria:
        if not c.strip(): continue #skip empty lines
        c=c.split(',')
        if len(c)==1: c[1]='asc'

        criteria.append(c)

    sortCriteria = criteria


workflow_tool=context.portal_workflow

def cmp(a,b):
    for field,order in sortCriteria:
        if hasattr(a,field) and hasattr(b,field):
            aval=getattr(a,field)
            if callable(aval): aval = aval()
            bval=getattr(b,field)
            if callable(bval): bval = bval()
            
            if order == 'desc':
                aval,bval = bval,aval
                
            try:    #if they are strings, lower them
                aval=aval.lower()
                bval=bval.lower()
            except:
                pass
    
            if aval < bval:
                return -1
            elif bval < aval:
                return 1
    return 0
        
    if a.isPrincipiaFolderish and not b.isPrincipiaFolderish:
        return -1
    elif b.isPrincipiaFolderish and not a.isPrincipiaFolderish:
        return 1
    
    if a.Title < b.Title:
        return -1
    elif b.Title < a.Title:
        return 1
    
    return 0

def checkPublished(o):
    # checks if an object is published respecting its 
    # publishing dates
    # XXX I did not find this in the API but there 
    # should be something like this....
    
    try:
        if workflow_tool.getInfoFor(o,'review_state','') != 'published':
            return 0
    
        now = context.ZopeTime()
        start_pub = getattr(o,'effective_date',None)
        end_pub   = getattr(o,'expiration_date',None)
        
        if start_pub and start_pub > now:
            return 0
        if end_pub and now > end_pub:
            return 0
    except:
        #if anything crashes dont publish it
        return 0
    
    return 1
    
#default function that finds the children out of a folderish object
def childFinder(obj,folderishOnly=1):
    user=obj.REQUEST['AUTHENTICATED_USER']
    try:

        if obj.meta_type in parentMetaTypesNotToQuery:
            return []
        
        # shall all Members be listed or just myself!
        if showMyUserFolderOnly and obj.id=='Members':
            try:
                return [getattr(obj,user.getId())]
            except:
                return []
        
        if obj.meta_type == 'Portal Topic':
            # to traverse through Portal Topics
            cat = getToolByName( obj, 'portal_catalog' )
            
            folderishOnly= not showTopicResults #in order to view all topic results in the tree 
    
            res=obj.listFolderContents()
            subs=obj.queryCatalog()
            
            # get the objects out of the cat results
            for s in subs:
                try:
                    o=context.restrictedTraverse(cat.getpath(s.data_record_id_))
                    res.append(wrap_obj(o,obj))
                except:
                    pass
            
        else:    
            #traversal to all 'CMFish' folders
            if hasattr(obj.aq_explicit,'listFolderContents'):
                res=obj.listFolderContents()
            else:
                #and all other *CMF* folders
                res=obj.contentValues()
        
        rs=[]
        for r in res: #filter out metatypes and by except:pass 
                      #all objs producing an error
            try:
                if r.meta_type not in metaTypesNotToList:
                    rs.append(r)
            except :
                pass

        res=rs

        # if wanted just keep folderish objects
        if folderishOnly:
            objs=filter(lambda x: hasattr(x.aq_explicit,'isPrincipiaFolderish') and x.aq_explicit.isPrincipiaFolderish,res)
            perm = 'View' #XXX should be imported
            permChk = context.portal_membership.checkPermission
            res = [o for o in objs if permChk(perm, o)] #XXX holy jeebus! this is expensive need to cache!

        if not user.has_role(rolesSeeUnpublishedContent,obj):  # the 'important' users may see unpublished content
            res = [o for o in res if checkPublished(o)]
        
    
        try:res.sort(cmp) #if sorting fails - never mind, it shall not break nav
        except:pass
        return res
    except :
        return []

tb=StatelessTreeBuilder(context,topObject=tree_root,childFinder=childFinder,
        includeTop=includeTop, 
        showFolderishSiblingsOnly=showFolderishSiblingsOnly, 
        showFolderishChildrenOnly=showFolderishChildrenOnly, 
        showNonFolderishObject=showNonFolderishObject,    
        topLevel=topLevel,
        )

res=tb.buildFlatMenuStructure(
    batchSize=batchSize, 
    batchStart=int(navBatchStart) #from where to start? is called automatically by the .pt
    )

for r in res['list']:
    r['published'] = checkPublished(r['object'])
    
return res
