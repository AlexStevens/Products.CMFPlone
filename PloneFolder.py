from Products.CMFCore.utils import _verifyActionPermissions, \
     getToolByName, getActionContext
from Products.CMFCore.Skinnable import SkinnableObjectManager
from OFS.Folder import Folder
from Products.CMFCore.CMFCatalogAware import CMFCatalogAware
from Products.CMFCore.CMFCorePermissions import View, ManageProperties, \
     ListFolderContents
from Products.CMFCore.CMFCorePermissions import AddPortalFolders, \
     AddPortalContent, ModifyPortalContent
from Products.CMFDefault.SkinnedFolder import SkinnedFolder
from Products.CMFDefault.DublinCore import DefaultDublinCoreImpl
from Products.CMFCore.interfaces.DublinCore import DublinCore as IDublinCore
from Products.CMFCore.interfaces.Contentish import Contentish as IContentish
from AccessControl import Permissions, getSecurityManager, \
     ClassSecurityInfo, Unauthorized
from Products.CMFCore import CMFCorePermissions
from Acquisition import aq_base, aq_inner, aq_parent
from Globals import InitializeClass
from webdav.WriteLockInterface import WriteLockInterface
from types import StringType

# this import can change with Zope 2.7 to
try:
    from OFS.IOrderSupport import IOrderedContainer as IZopeOrderedContainer
    hasZopeOrderedSupport=1
except ImportError:
    hasZopeOrderedSupport=0
# atm its safer defining an own
from interfaces.OrderedContainer import IOrderedContainer

# from Products.BTreeFolder2.BTreeFolder2 import BTreeFolder2Base

from OFS.ObjectManager import REPLACEABLE, BeforeDeleteException
from ComputedAttribute import ComputedAttribute

from PloneUtilities import log

class ReplaceableWrapper:
    """ A wrapper around an object to make it replaceable """
    def __init__(self, ob):
        self.__ob = ob

    def __getattr__(self, name):
        if name == '__replaceable__':
            return REPLACEABLE
        return getattr(self.__ob, name)

factory_type_information = { 'id'             : 'Folder'
                             , 'meta_type'      : 'Plone Folder'
                             , 'description'    : """\
Plone folders can define custom 'view' actions, or will behave like directory listings without one defined."""
                             , 'icon'           : 'folder_icon.gif'
                             , 'product'        : 'CMFPlone'
                             , 'factory'        : 'addPloneFolder'
                             , 'filter_content_types' : 0
                             , 'immediate_view' : 'folder_listing'
                             , 'actions'        :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View'
                                  , 'action'        : 'string:${folder_url}/'
                                  , 'permissions'   :
                                     (CMFCorePermissions.View,)
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'local_roles'
                                  , 'name'          : 'Local Roles'
                                  , 'action'        : 'string:${folder_url}/folder_localrole_form'
                                  , 'permissions'   :
                                     (CMFCorePermissions.ManageProperties,)
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'edit'
                                  , 'name'          : 'Edit'
                                  , 'action'        : 'string:${folder_url}/folder_edit_form'
                                  , 'permissions'   :
                                     (CMFCorePermissions.ManageProperties,)
                                  , 'category'      : 'folder'
                                  }
                                , { 'id'            : 'folderlisting'
                                  , 'name'          : 'Folder Listing'
                                  , 'action'        : 'string:${folder_url}/folder_listing'
                                  , 'permissions'   :
                                     (CMFCorePermissions.View,)
                                  , 'category'      : 'folder'
                                  , 'visible'       : 0
                                  }
                                )
                             }



class OrderedContainer(Folder):

    if hasZopeOrderedSupport:
        # got the IOrderedContainer interface from zope 2.7, too
        # make shure this implementation fullfilles both interfaces
        __implements__  = (IOrderedContainer, IZopeOrderedContainer)
    else:
        __implements__  = (IOrderedContainer,)

    security = ClassSecurityInfo()

    security.declareProtected(ModifyPortalContent, 'moveObject')
    def moveObject(self, id, position):
        obj_idx  = self.getObjectPosition(id)
        if obj_idx == position:
            return None
        elif position < 0:
            position = 0

        metadata = list(self._objects)
        obj_meta = metadata.pop(obj_idx)
        metadata.insert(position, obj_meta)
        self._objects = tuple(metadata)

    # here the implementing of IOrderedContainer starts
    # if plone sometime depends on zope 2.7 it should be replaced by mixing in
    # the 2.7 specific class OSF.OrderedContainer.OrderedContainer

    security.declareProtected(ModifyPortalContent, 'moveObjectsByDelta')
    def moveObjectsByDelta(self, ids, delta):
        """ Move specified sub-objects by delta.
        """
        if type(ids) is StringType:
            ids = (ids,)
        min_position = 0
        #objects = list(self._objects)
        obj_visible = []
        obj_hidden =[]
        obj_dict = {}

        types_tool = getToolByName(self, 'portal_types')
        types=types_tool.listContentTypes(by_metatype=1)

        for obj in self._objects:
            # sort out in portal visible and invisible objects in 2 lists
            try:
                types.index(obj['meta_type'])
            except ValueError:
                obj_hidden.append(obj)
            else:
                obj_dict[ obj['id'] ] = obj
                obj_visible.append(obj)


        # unify moving direction
        if delta > 0:
            ids = list(ids)
            ids.reverse()
            obj_visible.reverse()
        counter = 0

        for id in ids:
            try:
                object = obj_dict[id]
            except KeyError:
                raise ValueError('The object with the id "%s" does not exist.'
                                 % id)
            old_position = obj_visible.index(object)
            new_position = max( old_position - abs(delta), min_position )
            if new_position == min_position:
                min_position += 1
            if not old_position == new_position:
                obj_visible.remove(object)
                obj_visible.insert(new_position, object)
                counter += 1

        if counter > 0:
            if delta > 0:
                obj_visible.reverse()
            self._objects = tuple(obj_hidden + obj_visible)

        return counter


    security.declareProtected(ModifyPortalContent, 'getObjectPosition')
    def getObjectPosition(self, id):

        objs = list(self._objects)
        om = [objs.index(om) for om in objs if om['id']==id ]

        if om: # only 1 in list if any
            return om[0]

        raise NotFound('Object %s was not found'%str(id))

    security.declareProtected(ModifyPortalContent, 'moveObjectsUp')
    def moveObjectsUp(self, ids, delta=1, RESPONSE=None):
        """ Move an object up """
        self.moveObjectsByDelta(ids, -delta)
        if RESPONSE is not None:
            RESPONSE.redirect('manage_workspace')

    security.declareProtected(ModifyPortalContent, 'moveObjectsDown')
    def moveObjectsDown(self, ids, delta=1, RESPONSE=None):
        """ move an object down """
        self.moveObjectsByDelta(ids, delta)
        if RESPONSE is not None:
            RESPONSE.redirect('manage_workspace')

    security.declareProtected(ModifyPortalContent, 'moveObjectsToTop')
    def moveObjectsToTop(self, ids, RESPONSE=None):
        """ move an object to the top """
        self.moveObjectsByDelta( ids, -len(self._objects) )
        if RESPONSE is not None:
            RESPONSE.redirect('manage_workspace')

    security.declareProtected(ModifyPortalContent, 'moveObjectsToBottom')
    def moveObjectsToBottom(self, ids, RESPONSE=None):
        """ move an object to the bottom """
        self.moveObjectsByDelta( ids, len(self._objects) )
        if RESPONSE is not None:
            RESPONSE.redirect('manage_workspace')

    security.declareProtected(ModifyPortalContent, 'moveObjectToPosition')
    def moveObjectToPosition(self, id, position):
        """ Move specified object to absolute position.
        """
        delta = position - self.getObjectPosition(id)
        return self.moveObjectsByDelta(id, delta)

    security.declareProtected(ModifyPortalContent, 'orderObjects')
    def orderObjects(self, key, reverse=None):
        """ Order sub-objects by key and direction.
        """
        ids = [ id for id, obj in sort( self.objectItems(),
                                        ( (key, 'cmp', 'asc'), ) ) ]
        if reverse:
            ids.reverse()
        return self.moveObjectsByDelta( ids, -len(self._objects) )

    # here the implementing of IOrderedContainer ends


    def manage_renameObject(self, id, new_id, REQUEST=None):
        " "
        objidx = self.getObjectPosition(id)
        method = OrderedContainer.inheritedAttribute('manage_renameObject')
        result = method(self, id, new_id, REQUEST)
        self.moveObject(new_id, objidx)

        return result

InitializeClass(OrderedContainer)


class BasePloneFolder ( SkinnedFolder, DefaultDublinCoreImpl ):
    security=ClassSecurityInfo()

    __implements__ =  DefaultDublinCoreImpl.__implements__ + \
                      (SkinnedFolder.__implements__,WriteLockInterface)

    manage_options = Folder.manage_options + \
                     CMFCatalogAware.manage_options
    # fix permissions set by CopySupport.py
    __ac_permissions__=(
        ('Modify portal content',
         ('manage_cutObjects', 'manage_copyObjects', 'manage_pasteObjects',
          'manage_renameForm', 'manage_renameObject', 'manage_renameObjects',)),
        )

    def __init__(self, id, title=''):
        DefaultDublinCoreImpl.__init__(self)
        self.id=id
        self.title=title

    def __call__(self):
        """ Invokes the default view. """
        view = _getViewFor(self, 'view', 'folderlisting')
        if getattr(aq_base(view), 'isDocTemp', 0):
            return apply(view, (self, self.REQUEST))
        else:
            return view()

    def index_html(self):
        """ Acquire if not present. """
        _target = aq_parent(aq_inner(self)).aq_acquire('index_html')
        return ReplaceableWrapper(aq_base(_target).__of__(self))

    index_html = ComputedAttribute(index_html, 1)

    security.declareProtected(AddPortalFolders, 'manage_addPloneFolder')
    def manage_addPloneFolder(self, id, title='', REQUEST=None):
        """ adds a new PloneFolder """
        ob=PloneFolder(id, title)
        self._setObject(id, ob)
        if REQUEST is not None:
            #XXX HARDCODED FIXME!
            return self.folder_contents(self, REQUEST,
                                        portal_status_message='Folder added')

    manage_addFolder = manage_addPloneFolder
    manage_renameObject = SkinnedFolder.manage_renameObject

    security.declareProtected(Permissions.delete_objects, 'manage_delObjects')
    def manage_delObjects(self, ids=[], REQUEST=None):
        """ We need to enforce security. """
        mt=getToolByName(self, 'portal_membership')
        if type(ids) is StringType:
            ids = [ids]
        for id in ids:
            item = self._getOb(id)
            if not mt.checkPermission(Permissions.delete_objects, item):
                raise Unauthorized, (
                    "Do not have permissions to remove this object")
        SkinnedFolder.manage_delObjects(self, ids, REQUEST=REQUEST)

    def __browser_default__(self, request):
        """ Set default so we can return whatever we want instead of
        index_html """
        return self.browserDefault()

    security.declarePublic('contentValues')
    def contentValues(self,
                      spec=None,
                      filter=None,
                      sort_on=None,
                      reverse=0):
        """ Able to sort on field """
        values=SkinnedFolder.contentValues(self, spec=spec, filter=filter)
        if sort_on is not None:
            values.sort(lambda x, y, sort_on=sort_on: safe_cmp(getattr(x,sort_on),
                                                               getattr(y,sort_on)))
        if reverse:
            values.reverse()

        return values

    security.declareProtected( ListFolderContents, 'listFolderContents')
    def listFolderContents( self, spec=None, contentFilter=None, suppressHiddenFiles=0 ):
        """
        Hook around 'contentValues' to let 'folder_contents'
        be protected.  Duplicating skip_unauthorized behavior of dtml-in.

        In the world of Plone we do not want to show objects that begin with a .
        So we have added a simply check.  We probably dont want to raise an
        Exception as much as we want to not show it.

        """

        items = self.contentValues(spec=spec, filter=contentFilter)
        l = []
        for obj in items:
            id = obj.getId()
            v = obj
            try:
                if suppressHiddenFiles and id[:1]=='.':
                    raise Unauthorized(id, v)
                if getSecurityManager().validate(self, self, id, v):
                    l.append(obj)
            except (Unauthorized, 'Unauthorized'):
                pass
        return l

InitializeClass(BasePloneFolder)

class PloneFolder( BasePloneFolder, OrderedContainer ):
    meta_type = 'Plone Folder'

    __implements__ = BasePloneFolder.__implements__ + \
                     OrderedContainer.__implements__

    manage_renameObject = OrderedContainer.manage_renameObject

InitializeClass(PloneFolder)

def safe_cmp(x, y):
    if callable(x): x=x()
    if callable(y): y=y()
    return cmp(x,y)

manage_addPloneFolder=PloneFolder.manage_addPloneFolder
def addPloneFolder( self, id, title='', description='', REQUEST=None ):
    """ adds a Plone Folder """
    sf = PloneFolder(id, title=title)
    sf.description=description
    self._setObject(id, sf)
    if REQUEST is not None:
        REQUEST['RESPONSE'].redirect( sf.absolute_url() + '/manage_main' )

#--- Helper function that can figure out what 'view' action to return
def _getViewFor(obj, view='view', default=None):

    ti = obj.getTypeInfo()
    context = getActionContext(obj)
    if ti is not None:
        actions = ti.listActions()
        for action in actions:
            _action = action.getAction(context)
            if _action.get('id', None) == default:
                default=action
            if _action.get('id', None) == view:
                target=_action['url']
                if target.startswith('/'):
                    target = target[1:]
                if _verifyActionPermissions(obj, action) and target!='':
                    __traceback_info__ = ( ti.getId(), target )
                    computed_action = obj.restrictedTraverse(target)
                    if computed_action is not None:
                        return computed_action

        if default is not None:
            _action = default.getAction(context)
            if _verifyActionPermissions(obj, default):
                target=_action['url']
                if target.startswith('/'):
                    target = target[1:]
                __traceback_info__ = ( ti.getId(), target )
                return obj.restrictedTraverse(target)

        # "view" action is not present or not allowed.
        # Find something that's allowed.
        #for action in actions:
        #    if _verifyActionPermissions(obj, action)  and action.get('action','')!='':
        #        return obj.restrictedTraverse(action['action'])
        raise 'Unauthorized', ('No accessible views available for %s' %
                               '/'.join(obj.getPhysicalPath()))
    else:
        raise 'Not Found', ('Cannot find default view for "%s"' %
                            '/'.join(obj.getPhysicalPath()))
