#!/usr/bin/env python
import os, sys
import subprocess, urllib, re

bundle_lib_path = os.environ['TM_BUNDLE_SUPPORT'] + '/lib'
sys.path.insert(0, bundle_lib_path)

tm_support_path = os.environ['TM_SUPPORT_PATH'] + '/lib'
if tm_support_path not in sys.path:
    sys.path.insert(0, tm_support_path)

from tm_helpers import to_plist, from_plist, current_word

import rope.base.simplify
from rope.base import project,libutils
from rope.contrib import codeassist, autoimport
from rope.refactor.extract import ExtractMethod
from rope.refactor.importutils import ImportOrganizer
from rope.refactor.rename import Rename
import rope.base.simplify
import rope.base.simplify

TM_DIALOG = os.environ['DIALOG_1']
TM_DIALOG2 = os.environ['DIALOG']

def tooltip(text):
    options = {'text':str(text)}
    call_dialog(TM_DIALOG2+" tooltip", options)

def register_completion_images():
    icon_dir = os.environ['TM_BUNDLE_SUPPORT'] + '/icons'
    
    images = {
        "function"   : icon_dir+"/Function.png",
        "instance" : icon_dir+"/Property.png",
        "class"   : icon_dir+"/Class.png",
        "module"    : icon_dir+"/Module.png",
        "None"    : icon_dir+"/None.png",
    }
    call_dialog(TM_DIALOG2+" images", {'register' : images})

def current_identifier():
    return current_word(r"[A-Za-z_0-9]*")

def identifier_before_dot():
    word = current_word(r"^[\.A-Za-z_0-9]*", direction='left')
    if word:
        return word[:-1]
    return ""
    
def completion_popup(proposals):
    register_completion_images()
    command = TM_DIALOG2+" popup"
    word = current_identifier()
    if word:
        command += " --alreadyTyped "+word
       
    options = [dict([['display',p.name], 
                    ['image', p.type if p.type else "None"]])
                    for p in proposals]
    call_dialog(command, {'suggestions' : options})
        

def call_dialog(command, options=None, shell=True):
    popen = subprocess.Popen(
                 command,
                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,shell=shell)
    if options:
        out, _ = popen.communicate(to_plist(options))
    else:
        out, _ = popen.communicate()
    return out
    
def get_input(title="Input",default=""):
    if os.environ.get('TM_RopeMate_HUD', False):
        nib = os.environ['TM_BUNDLE_SUPPORT']+"/input_hud"
    else:
        nib = os.environ['TM_BUNDLE_SUPPORT']+"/input"
    out = call_dialog([TM_DIALOG, '-cm', nib], {'title':title, 'result':default}, False)
    if not out:
        return None
    return from_plist(out).get('result', None)

def caret_position(code):
    lines = code.split("\n")
    line_lengths = [len(l)+1 for l in lines]
    line_number = int(os.environ['TM_LINE_NUMBER'])
    line_index = int(os.environ['TM_LINE_INDEX'])
    offset = sum(line_lengths[0:line_number-1]) + line_index
    return offset

def init_from_env():
    project_dir = os.environ.get('TM_PROJECT_DIRECTORY', None)
    file_path = os.environ['TM_FILEPATH']

    if project_dir:
        myproject = project.Project(project_dir)
        myresource = libutils.path_to_resource(myproject, file_path)
    else:
        #create a single-file project (ignoring all other files in the file's folder)
        folder = os.path.dirname(file_path)
        ignored_res = os.listdir(folder)
        ignored_res.remove(os.path.basename(file_path))
        myproject = project.Project(
            ropefolder=None,projectroot=folder, ignored_resources=ignored_res)
        
        myresource = libutils.path_to_resource(myproject, file_path)
        
    code = sys.stdin.read()
    return myproject, myresource, code

def autocomplete():
    project, resource, code = init_from_env()
    offset = caret_position(code)
    pid = os.fork()
    result = ""
    if pid == 0:
        try:
            raw_proposals = codeassist.code_assist(project, code, offset, resource)
            sorted_proposals = codeassist.sorted_proposals(raw_proposals)
            proposals = filter(lambda p: p.name != "self=", sorted_proposals)
            if len(proposals) == 0:
                proposals = simple_module_completion()
            if len(proposals) == 0:
                tooltip("No completions found!")
            else:
                completion_popup(proposals)
        except Exception, e:
            tooltip(e)
    return result
    
def simple_module_completion():
    """tries a simple hack (import+dir()) to help completion of imported c-modules"""
    result = []
    try:
        name = identifier_before_dot()
        if not name:
            return []
            
        module = None
        try:
            __import__(name)
            module = sys.modules[name]
        except:
            return []

        names = dir(module)
        for name in names:
            if not name.startswith("__"):
                p = rope.contrib.codeassist.CompletionProposal(
                    name, "imported", rope.base.pynames.UnboundName())
                type_name = type(getattr(module, name)).__name__
                if type_name.find('function') != -1 or type_name.find('method') != -1:
                    p.type = 'function'
                elif type_name == 'module':
                    p.type = 'module'
                elif type_name == 'type':
                    p.type = 'class'
                else:
                    p.type = 'instance'
                result.append(p)

    except Exception, e:
        print e
        return []
    return result
    
def extract_method():
    project, resource, code = init_from_env()
    try:
        offset_length = len(os.environ.get('TM_SELECTED_TEXT', ''))
        if offset_length == 0:
            tooltip("You have to selected some code to extract it as a method")
            return code
        offset = caret_position(code)-offset_length
        extractor = ExtractMethod(project, resource, offset, offset+offset_length)
    
        func_name = get_input("Extracted method's name")
        if func_name is None:
            tooltip("Enter a name for the extraced function!")
            return code
        changes = extractor.get_changes(func_name)
        result = changes.changes[0].new_contents
    except Exception, e:
        tooltip(e)
        return code
    
    return result

def rename():
    project, resource, code = init_from_env()
    
    if current_identifier == "":
        tooltip("Select an identifier to rename")
        return code
    
    offset = caret_position(code)
    try:
        rename = Rename(project, resource, offset)
        
        func_name = get_input(title="New name",default=rename.old_name)
        if func_name is None or func_name == rename.old_name:
            tooltip("Enter a new name!")
            return code
        
        changes = rename.get_changes(func_name, in_hierarchy=True)
        # remove the current file from the changeset.
        # we will apply the changes to this file manually,
        # (as the result of the TM Command) to keep TM's undo history in order
        current_file_changes = filter_changes_in_current_file(changes,resource)
        result = current_file_changes.new_contents
        # apply changes to all other files
        project.do(changes)
    except Exception, e:
        tooltip(e)
        result = code
    
    return result

def goto_definition():
    project, _ , code = init_from_env()
    offset = caret_position(code)
    found_resource, line = None, None
    try:
        found_resource, line = codeassist.get_definition_location(project, code, offset)
    except rope.base.exceptions.BadIdentifierError, e:
        # fail silently -> the user selected empty space etc
        pass 
    except Exception, e:
        tooltip(e)
    
    if found_resource is not None:
        return 'txmt://open?url=file://%s&line=%d' % (
                urllib.quote(found_resource.real_path), line)
    elif line is not None:
        return 'txmt://open?line=%d' % line
    return ''

def filter_changes_in_current_file(changes,resource):
    change_for_current_file = [f for f in changes.changes
                                if f.resource == resource][0]
    changes.changes.remove(change_for_current_file)
    return change_for_current_file

def organize_imports():
    project, resource, code = init_from_env()
    result = code
    try:
        organizer = ImportOrganizer(project)
        
        operations = [organizer.organize_imports,
                    organizer.handle_long_imports,
                    organizer.expand_star_imports]
        # haven't found a way to easily combine the changes in-memory
        # so i commit all of them and then return the changed file's content
        for op in operations:
            change = op(resource)
            if change:
                project.do(change)
    
        with open(resource.real_path, "r") as f:
            result = f.read()
    except Exception, e:
        tooltip(e)
    return result
    
def complete_import(project, resource, code, offset):
    class ImportProposal(object):
        def __init__(self, name, module):
            self.name = name
            self.display = name + " - " + module
            self.insert = module+"."+name
            self.module = module
            self.type = 'module'

    importer = autoimport.AutoImport(project=project, observe=False)
    importer.generate_cache()
    proposals = importer.import_assist(starting=current_identifier())
    if len(proposals) == 0:
        return []
    else:
        return [ImportProposal(p[0], p[1]) for p in proposals]
    
def find_imports():
    def find_last_import_line(lines):
        x = 0
        for i in range(len(lines)):
            l = lines[i]
            if l.startswith("from") or l.startswith("import"):
                x = i
        return x
    
    project, resource, code = init_from_env()
    offset = caret_position(code)
    pid = os.fork()
    result = ""
    if pid == 0:
        try:
            proposals = complete_import(project, resource, code, offset)
            if len(proposals) == 0:
                tooltip("No completions found!")
            else:
                register_completion_images()
                command = TM_DIALOG2+" popup"
                word = current_identifier()
                if word:
                    command += " --alreadyTyped "+word
                command += " --returnChoice"
                options = [dict([['display',p.display], 
                                ['image', p.type if p.type else "None"],
                                ['match', p.name],
                                ['module', p.module]])
                                for p in proposals]
                
                out = call_dialog(command, {'suggestions' : options})

                # from_plist parses only xml-plists, but dialog returns old-style ascii plists
                try: 
                    import_from_mod_name = re.search(r'module = "(.*)";', out).group(1)
                except:
                    import_from_mod_name = re.search(r'module = ".*";', out).group(1)
                try:
                    import_name = re.search(r'match = "(.*)";', out).group(1)
                except:
                    import_name = re.search(r'match = (.*);', out).group(1)
                
                typed_len = len(word)
                full_name = import_from_mod_name+"."+import_name
                code = code[:offset-typed_len] + full_name + code[offset:]
                lines = code.split("\n")
                idx = find_last_import_line(lines)
                new_line = "import "+import_from_mod_name
                tooltip("Added \""+new_line+"\"at line "+str(idx+1))
                lines = lines[:idx+1]+[new_line]+lines[idx+1:]
                result = "\n".join(lines)
        except Exception, e:
            tooltip(e)
    return result
    

def main():
    operation = {'extract_method'   : extract_method,
                'rename'            : rename,
                'autocomplete'      : autocomplete,
                'goto_definition'   : goto_definition,
                'organize_imports'  : organize_imports,
                'find_imports'      : find_imports}\
                .get(sys.argv[1])
    sys.stdout.write(operation())

if __name__ == '__main__':
    main()