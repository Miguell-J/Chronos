import argparse
from ast import arg
import configparser
from datetime import datetime
import grp, pwd
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
from tarfile import data_filter
import zlib

from gpg import Data

argparser = argparse.ArgumentParser(description="Chronos - my GIT.")
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
argsubparsers.required = True

def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    match args.command:
        case "add": cmd_add(args)
        case "cat-file": cmd_cat_file(args)
        case "check-ignore": cmd_check_ignore(args)
        case "checkout": cmd_checkout(args)
        case "commit": cmd_commit(args)
        case "hash-object": cmd_hash_object(args)
        case "init": cmd_init(args)
        case "log": cmd_log(args)
        case "ls-files": cmd_ls_files(args)
        case "ls-tree": cmd_ls_tree(args)
        case "rev-parse": cmd_rev_parse(args)
        case "rm": cmd_rm(args)
        case "show-ref": cmd_show_ref(args)
        case "status": cmd_status(args)
        case "tag": cmd_tag(args)
        case _ : print(f"Unknown command")
         
class GitRepository (object):
    """ 
    A git repository object that contains all the methods to interact with a git repository.
    """

    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.exists(self.gitdir)):
            raise Exception(f"Not a git repository: {path}")
        
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuraation file missing")
        
        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception(f"Unsupported repository format version: {vers}")

def repo_path(repo, *path):
    """
    Compute path under repo's git directory.
    If path is empty, return the git directory itself.
    If path is not empty, join the git directory with the given path.
    If the path is relative, it is joined with the git directory.
    If the path is absolute, it is returned as is.
    If the path is a file, it is returned as is.
    If the path is a directory, it is joined with the git directory.
    If the path is a file in the git directory, it is returned as is.
    If the path is a directory in the git directory, it is returned as is.
    If the path is a file in the worktree, it is returned as is.
    """
    return os.path.join(repo.gitdir, *path)

def repo_file(repo, *path, mkdir=False):
    """
    Same as repo_path, but create dirname(*path) if absent. For example, repo_file(r, \"refs\", \"remotes\", \"origin\", \"HEAD\") will create .git/refs/remotes/origin."""
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)
    
def repo_dir(repo, *path, mkdir=False):
    """
    Same as repo_path, but create dirname(*path) if absent. For example, repo_dir(r, \"refs\", \"remotes\", \"origin\") will create .git/refs/remotes/origin.
    If mkdir is True, create the directory if it does not exist.
    """
    path = repo_path(repo, *path)

    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception(f"Not a directory: {path}")
        
    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None
    
def repo_create(path):
    """
    Create a new repository at path.
    """

    repo = GitRepository(path, True)

    # First, we make sure the path either doesn't exist or is empty.

    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"Is not a directory: {path}")
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception(f"Directory not empty: {repo.gitdir}")
    else:
        os.makedirs(repo.worktree)

    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo, "objects", mkdir=True)
    assert repo_dir(repo, "refs", "tags", mkdir=True)
    assert repo_dir(repo, "refs", "heads", mkdir=True)

    # .git/description is not used by git, but we create it for compatibility with other tools.
    with open(repo_file(repo, "description"), "w") as f:
        f.write("Unnamed repository; edit this file 'description' to name the repository.\n")

    # .git/HEAD is a file that points to the current branch.
    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    # .git/config is a file that contains the configuration of the repository.
    with open(repo_file(repo, "config"), "w") as f:
        config = repo_default_config()
        config.write(f)

    return repo

def repo_default_config():
    """
    Return a default configuration for a new repository.
    This configuration is used when creating a new repository.
    It contains the core section with the repository format version, file mode, and bare status.
    """
    ret = configparser.ConfigParser()

    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")

    return ret

argsp = argsubparsers.add_parser("init", help="Create an empty git repository at the given path.")

argsp.add_argument("path",
                   metavar="directory",
                   nargs="?",
                   default=".",
                   help="The path to the directory where the repository will be created. Defaults to the current directory.")

def cmd_init(args):
    repo_create(args.path)

def repo_find(path=".", required=True):
    """
    Find a git repository starting from the given path.
    If required is True, raise an exception if no repository is found.
    If required is False, return None if no repository is found.
    """
    path = os.path.realpath(path)

    if os.path.isdir(os.path.join(path, ".git")):
        return GitRepository(path)
    
    # If we haven't returned, recurse in parent if w
    parent = os.path.realpath(os.path.join(path, ".."))
    if parent == path:
        # Botton case
        # os.path.join("/", "..") == "/":
        # if parent == path, we are at the root of the filesystem.
        if required:
            raise Exception(f"No git repository found in {path} or any parent directory.")
        else:
            return None
        
    # recursive case
    return repo_find(parent, required)

class GitObject (object):
    """
    A git object is a file in the .git/objects directory.
    It has a type (blob, tree, commit, tag) and a hash.
    The hash is the SHA-1 hash of the object content.
    The type is stored in the first line of the object file.
    The content is stored in the rest of the file.
    """

    def __init__(self, data= None):
        if data != None:
            self.deserialize(data)
        else:
            self.init()

    def serialize(self, repo):
        """This function MUST be implemented by subclasses.

        It must read the object's contents from self.data, a byte string, and
        do whatever it takes to convert it into a meaningful representation.
        What exactly that means depend on each subclass."""

        raise Exception("Unimplemented!")
    
    def deserialize(self, data):
        raise Exception("Unimplemented!")
    
    def init(self):
        pass # Just do nothing, this is a reasonable default for some objects.

def object_read(repo, sha):
    """
    Read a git object from the repository.
    The sha is the SHA-1 hash of the object.
    The object is read from the .git/objects directory.
    If the object does not exist, raise an exception.
    Read object sha from Git repository repo.  Return a
    GitObject whose exact type depends on the object.
    """
    path = repo_file(repo, "objects", sha[0:2], sha[2:])

    if not os.path.isfile(path):
        return None
    
    with open (path, "rb") as f:
        raw = zlib.decompress(f.read())
    # The first line of the object is the type and size.

    x = raw.find(b' ')
    fmt = raw[0:x]

    # read and validate the object size

    y = raw.find(b'\x00', x)
    size = int(raw[x:y].decode("ascii"))

    if size != len(raw)-y-1:
        raise Exception(f"Malinformed object {sha}: bad length")
    
    # Pick constructor
    match fmt:
        case b'commit' : c=GitCommit
        case b'tree' : c=GitTree
        case b'blob' : c=GitBlob
        case b'tag' : c=GitTag
        case _ : raise Exception(f"Unknown object type {fmt.decode('ascii')}")

    # Call constructor and return object

    return c(raw[y+1:])
    
def object_write(obj, repo=None):
    """
    Write a git object to the repository.
    The object is serialized and written to the .git/objects directory.
    The SHA-1 hash of the object is returned.
    If repo is None, the object is written to the current repository.
    """
    
    #serialize
    data = obj.serialize()

    #add header
    result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data

    #compute hash
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        # compute path
        path=repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)
        # write object
        if not os.path.exists(path):
            with open(path, 'wb') as f:
                # compress and write the object
                f.write(zlib.compress(result))

    return sha

class GitBlob(GitObject):
    """
    A git blob object is a file in the .git/objects directory.
    It contains the content of a file.
    """

    fmt = b'blob'

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data

argsp = argsubparsers.add_parser("cat-file", help="Provide content of the requested git object.")

argsp.add_argument("type",
                   metavar="type",
                   choices=["blob", "tree", "commit", "tag"],
                   help="The type of the object to show. One of: blob, tree, commit, tag.")
argsp.add_argument("object",
                   metavar="object",
                   help="The object to display the content of.")

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())

def cat_file(repo, obj, fmt=None):
    obj = object_read(repo, object_find, obj, fmt=fmt)
    sys.stdout.buffer.write(obj.serialize())

def object_find(repo, name, fmt=None, follow=True):
    """
    Find a git object in the repository.
    The name can be a SHA-1 hash, a tag, a branch, or a file.
    If fmt is not None, the object must be of that type.
    If follow is True, follow the object if it is a branch or a tag.
    If follow is False, return the object as is.
    If the object is not found, raise an exception.
    """

    sha = object_resolve(repo, name)

    if not sha:
        raise Exception(f"No such reference {name}.")
    
    if len(sha) > 1:
        raise Exception(f"Ambiguous reference {name}: Candidates are:\n - {'\n - '.join(sha)}.")
    
    sha = sha[0]

    if not fmt:
        return sha
    
    while True:
        obj = object_read(repo, sha)
        #     ^^^^^^^^^^ < this is a bit agressive(ulala): we are reading
        # the full object just to get its type, and we are doing that in a 
        # loop, albeit normally short. Dont expect high performance here (mayba we can do something here???)

        if obj.fmt == fmt:
            return sha
        
        if not follow:
            return None
        
        #follow tags
        if obj.fmt == b'tag':
            sha = obj.kvlm[b'object'].decode("ascii")

        elif obj.fmt == b'commit' and fmt == b'tree':
            sha = obj.kvlm[b'tree'].decode("ascii")

        else:
            return None

argsp = argsubparsers.add_parser("hash-object",
                                 help="Compute the object ID and optionally create a blob from a file.")

argsp.add_argument("-t",
                   metavar="type",
                   dest="type",
                   choices=["blob", "tree", "commit", "tag"],
                   default="blob",
                   help="Especify the typw of the object")
argsp.add_argument("-w",
                   dest="write",
                   action="store_true",
                   help="Write the object to the repository. If not specified, just compute the hash.")
argsp.add_argument("path",
                   help="Read object from <file>")

def cmd_hash_object(args):
    if args.write:
        repo = repo_find()
    else:
        repo = None

    with open(args.path, "rb") as f:
        sha = object_hash(f, args.type.encode(), repo)
        print(sha)

def object_hash(fd, fmt, repo=None):
    data = fd.read()

    #choose constructor
    match fmt:
        case b'commit' : obj=GitCommit(data)
        case b'tree' : obj=GitTree(data)
        case b'blob' : obj=GitBlob(data)
        case b'tag' : obj=GitTag(data)
        case _ : raise Exception(f"Unknown object type {fmt}!")

    return object_write(obj, repo)

def kvlm_parse(raw, start=0, dct=None):
    """
    Parse a key-value list message from a byte string.
    The message is a sequence of key-value pairs, where each pair is separated by a newline.
    The key is a byte string, followed by a space, and the value is a byte string that may span multiple lines.
    If the value spans multiple lines, the continuation lines start with a space.
    The last line of the message is a blank line, which indicates the end of the message.
    The function returns a dictionary with the key-value pairs.
    If the message is empty, the function returns an empty dictionary.
    If the message is malformed, the function raises an exception.
    If dct is provided, it is used to store the key-value pairs. Otherwise, a new dictionary is created.
    """
    if not dct:
        dct = dict()
        # You cannot declare the argument as dct=dict() or all call to the function will endlessly grow the same dict

    # This function is recursive: it it reads reads a key/value pair, then call itself back with the new position. So we need to know where we are: at a keyword, or already in teh messageQ

    # we search for the next spacce and the next newline
    spc = raw.find(b' ', start)
    nl = raw.find(b'\n', start)

    # If space appears before newline, we have a keyword. Otherwise it's the final message, wich we just read to the end of the file

    #Base case
    # =========
    # If newline appears first (or there's no space at all, in which case find returns -1), we assune a blanck line. A blanck means the remainder of teh data is the message. We store it in the dictionary, with None as the key, and return
    if (spc < 0) or (nl < spc):
        assert nl ==  start
        dct[None] = raw[start+1:]
        return dct
    
    #recursive case
    #================
    # We read a key-value pair and recurse for the next one.
    key = raw[start:spc]

    # find the end of the value. Continuation lines begin with a space, so we loop until we find a "\n" not followed by a space
    end = start
    while True:
        end = raw.find(b'\n', end+1)
        if raw[end+1] != ord(' '): break

    # Grab the value
    # Also drop the leading space on continuation lines
    value = raw[spc+1:end].replace(b'\n ', b'\n')

    # Dont overwrite existing data contents
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [ dct[key], value ]

    else:
        dct[key] = value
    # Recurse for the next key-value pair
    return kvlm_parse(raw, start=end+1, dct=dct)

        
def kvlm_serialize(kvlm):
    ret = b''
    
    # output fields
    for k in kvlm.keys():
        #sky the message itself
        if k == None: continue
        val = kvlm[k]
        #normalize value to a list
        if type(val) != list:
            val = [ val ]

        for v in val:
            ret += k + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'

    # append a blank line to indicate the end of the message
    ret += b'\n' + kvlm[None]
    return ret

class GitCommit(GitObject):
    """
    A git commit object is a file in the .git/objects directory.
    It contains the metadata of a commit, such as the author, committer, date, and message.
    It also contains the SHA-1 hash of the tree object that represents the state of the repository at the time of the commit.
    """

    fmt = b'commit'

    def deserialize(self, data):
        """
        Deserialize a commit object from a byte string.
        The data is a key-value list message, where each line is a key-value pair.
        The keys are: 
        - tree: the SHA-1 hash of the tree object
        - parent: the SHA-1 hash of the parent commit (if any)
        """
        self.kvlm = kvlm_parse(data)

    def serialize(self):
        """ 
        Serialize a commit object to a byte string.
        The byte string is a key-value list message, where each line is a key-value pair.
        The keys are:
        - tree: the SHA-1 hash of the tree object
        - parent: the SHA-1 hash of the parent commit (if any)
        """
        return kvlm_serialize(self.kvlm)

    def init(self):
        """ Initialize a commit object with default values.
        The default values are:
        - tree: None
        - parent: None"""
        self.kvlm = dict()      

argsp = argsubparsers.add_parser("log",
                                 help="Display the commit log of the repository.")
argsp.add_argument("commit",
                   default="HEAD",
                   nargs="?",
                   help="The commit to start the log from. Defaults to HEAD.")

def cmd_log(args):
    repo = repo_find()
    print("digraph chronoslog {")
    print("  node[shape=rect]")
    log_graphviz(repo, object_find(repo, args.commit), set())
    print("}")

def log_graphviz(repo, sha, seen):
    if sha in seen:
        return
    seen.add(sha)

    commit = object_read(repo, sha)
    message = commit.kvlm[None].decode("utf8").strip()
    message = message.replace("\\", "\\\\")
    message = message.replace("\"", "\\\"")

    if "\n" in message: # keep only the first line
        message = message[:message.index("\n")]

    print(f"  c_{sha} [label=\]{sha[0:7]}: {message}\"]")
    assert commit.fmt==b'commit'

    if not b'parent' in commit.kvlm.keys():
        #base case: the initial commit
        return
    
    parents = commit.kvlm[b'parent']

    if type(parents) != list:
        parents = [ parents ]

    for p in parents:
        p = p.decode("ascii")
        print(f"  c_{sha} -> c_{p}")
        log_graphviz(repo, p, seen)
    
class GitTreeLeaf (object):
    """
    A git tree leaf is a file in the .git/objects directory.
    It contains the metadata of a file, such as the mode, path, and SHA-1 hash.
    It is used to represent a file in a tree object.
    """
    
    def __int__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha

def tree_parse_one(raw, start=0):
    # find the space terminator of the mode
    x = raw.find(b' ', start)
    assert x-start == 5 or x-start == 6

    #read the mode
    mode = raw[start:x]
    if len(mode) == 5:
        #normalize for 6 bytes
        mode = b'0' + mode

    #find the null terminator of the path
    y = raw.find(b'\x00', x)

    #and read the path
    path = raw[x+1:y]

    # and read the sha
    raw_sha = int.from_bytes[raw[y+1:y+21], 'big']

    # and convert it into a hex string, padded to 40 chars
    #with zeros if needed

    sha = format(raw_sha, "040x")
    return y+21, GitTreeLeaf(mode, path.decode("utf8"), sha)

def tree_parse(raw):
    """
    Parse a git tree object from a byte string.
    The data is a sequence of tree leaves, where each leaf is a mode, path, and SHA-1 hash.
    The leaves are separated by a null byte.
    The function returns a list of GitTreeleaf objects."""
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos, data = tree_parse_one(raw, pos)
        ret.append(data)

    return ret

# this is not a comparision func, but a conversion func, python default sort doent accept a custom sompariskon func, like in most languages, but a 'key' arg that return a new value, which is compared using the default rules. So we just return the leaf name, with an extra / if its a directory
def tree_leaf_sort_key(leaf):
    if leaf.mode.startswith(b'10'):
        return leaf.path
    else:
        return leaf.path + "/"
    
def tree_serialize(obj):
    """
    Serialize a git tree object to a byte string.
    The byte string is a sequence of tree leaves, where each leaf is a mode, path, and SHA-1 hash.
    The leaves are separated by a null byte.
    The function returns a byte string that can be written to a file.
    """
    obj.items.sort(key=tree_leaf_sort_key)
    ret = b''
    for i in obj.items:
        ret += i.mode
        ret += b' '
        ret += i.path.encode("utf8")
        ret += b'\x00'
        sha = int(i.sha, 16)
        ret += sha.to_bytes(20, byteorder='big')
    return ret

class GitTree(GitObject):
    """
    A git tree object is a file in the .git/objects directory.
    It contains the metadata of a directory, such as the mode, path, and SHA-1 hash.
    It is used to represent a directory in a commit object.
    """

    fmt = b'tree'

    def deserialize(self, data):
        self.items = tree_parse(data)

    def serialize(self):
        return tree_serialize(self)
    
    def init(self):
        self.items = list()

argsp = argsubparsers.add_parser("ls-tree", help="List the contents of a tree object.")
argsp.add_argument("-r", 
                   dest="recursive",
                   action="store_true",
                   help="List the contents of the tree recursively.")
argsp.add_argument("tree",
                   help="The tree object to list the contents of. Can be a SHA-1 hash, a branch, or a tag.")
def cmd_ls_tree(args):
    repo = repo_find()
    ls_tree(repo, args.tree, args.recursive)

def ls_tree(repo, ref, recursive=None, prefix=""):
    """_summary_

    Args:
        repo (_type_): _description_
        ref (_type_): _description_
        recursive (_type_, optional): _description_. Defaults to None.
        prefix (str, optional): _description_. Defaults to "".

    Raises:
        Exception: _description_

    Prints the contents of a tree object in a format similar to `ls -l`.
    The output is a list of files and directories, with their mode, type, SHA-1 hash, and path.
    If recursive is True, the contents of subdirectories are listed recursively.
    If recursive is False, only the contents of the top-level directory are listed.
    If recursive is None, the contents of the tree are listed without recursion.
    If the tree is a leaf, the contents are printed in a format similar to `ls -l`.
    If the tree is a branch, the contents are printed in a format similar to `ls -R`.
    """
    sha = object_find(repo, ref, fmt=b'tree')
    obj = object_read(repo, sha)
    for item in obj.items:
        if len(item.mode) == 5:
            type = item.mode[0:1]
        else:
            type = item.mode[0:2]
        match type:
            case b'10': type = "blob" #normal file
            case b'04': type = "tree"
            case b'12': type = "blob" #symlink
            case b'16': type = "commit"
            case _: raise Exception(f"Unknown mode {item.mode} in tree {sha}")

        if not (recursive and type=='tree'): #is a leaf
            print(f"{'0'*(6-len(item.mode))+item.mode.decode("ascii")}{type}{item.sha}\t{os.path.join(prefix, item.path)}")
        else: #this is a branch, recurse
            ls_tree(repo, item.sha, recursive, os.path.join(prefix, item.path))

argsp = argsubparsers.add_parser("checkout", help="Cheackout a commit into a directory.")
argsp.add_argument("commit",
                   help="The commit/tree to checkout")
argsp.add_argument("-f",
                   help="The empty directory to checkout")

def cmd_checkout(args):
    """_summary_

    Args:
        args (_type_): _description_

    Raises:
        Exception: _description_
        Exception: _description_

    Checkout a commit or tree into a directory.
    The commit can be a SHA-1 hash, a branch, or a tag.
    The directory must be empty, otherwise an exception is raised.
    If the directory does not exist, it is created.
    If the commit is a tree, the contents of the tree are checked out into the directory.
    If the commit is a commit, the tree of the commit is checked out into the directory.
    """
    repo = repo_find()

    obj = object_read(repo, object_find(repo, args.commit))

    # if its a commit, grab the tree
    if obj.fmt == b'commit':
        obj = object_read(repo, obj.kvlm[b'tree'].decode("ascii"))

    # verify that the path is empty, IMPORTANT, we do not want to overwrite or delete files!
    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception(f"Path {args.path} is not a directory")
        if os.listdir(args.path):
            raise Exception(f"Path {args.path} is not empty")
        
    # create the directory if it does not exist
    else:
        os.makedirs(args.path)

    tree_checkout(repo, obj, os.path.realpath(args.path))

def tree_checkout(repo, tree, path): 
    """_summary_

    Args:
        repo (_type_): _description_
        tree (_type_): _description_
        path (_type_): _description_

    Raises:
        Exception: _description_

    Checkout a tree object into a directory.
    The tree is a list of files and directories, each with a mode, path, and SHA-1 hash.
    The contents of the tree are checked out into the directory.
    If the item is a tree, a directory is created and the function is called recursively.
    If the item is a blob, the file is written to the directory.
    If the item is not a tree or a blob, an exception is raised.
    """
    for item in tree.items:
        obj = object_read(repo, item.sha)
        dest = os.path.join(path, item.path)

        if obj.fmt == b'tree':
            # if the item is a tree, create the directory and recurse
            os.mkdir(dest)
            tree_checkout(repo, obj, dest)
        elif obj.fmt == b'blob':
            # if the item is a blob, write the file
            with open(dest, "wb") as f:
                f.write(obj.blobdata)

def ref_resolve(repo, ref):
    """
    Resolve a reference to a git object.
    The reference can be a branch, a tag, or a commit.
    If the reference is a branch, the function returns the SHA-1 hash of the commit that the branch points to.
    If the reference is a tag, the function returns the SHA-1 hash of the commit that the tag points to.
    If the reference is a commit, the function returns the SHA-1 hash of the commit.
    If the reference is not found, the function returns None.
    If the reference is a symbolic reference, the function resolves the reference to the actual object.
    Args:
        repo (GitRepository): The repository to resolve the reference in.
        ref (str): The reference to resolve, e.g. "refs/heads/main" or "HEAD".
    Returns:
        str: The SHA-1 hash of the object that the reference points to, or None if the reference is not found.
    """
    path = repo_file(repo, ref)

    """
    sometimes, an indirect reference may be broken, this  is normal in one especifc case
    we are looking for head on a new repository with no commits, in that case, .git/HEAD points 
    to "ref: refs/heads/main", but .git/refsheads, main does not exist yet (since there is no commit to refer to
    so we return None, to indicate that the reference is not resolved.)
    """

    if not os.path.isfile(path):
        return None
    
    with open(path, 'r') as fp:
        data = fp.read()[:-1]
        #drop final \n ^^^^^^

    if data.startswith("ref: "):
        return ref_resolve(repo, data[5:])
    
    else:
        return data
    

def ref_list(repo, path=None):
    """_summary_

    Args:
        repo (_type_): _description_
        path (_type_, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """
    if not path:
        path = repo_dir(repo, "refs")

    ret = dict()

    #sort the output of listdir

    for f in sorted(os.listdir(path)):
        can = os.path.join(path, f)
        if os.path.isdir(can):
            ret[f] = ref_list(repo, can)
        else:
            ret[f] = ref_resolve(repo, can)

    return ret

argsp = argsubparsers.add_parser("show-ref", help="Show references in the repository.")

def cmd_show_ref(args):
    """_summary_

    Args:
        args (_type_): _description_
    """
    repo = repo_find()
    refs = ref_list(repo)
    show_ref(repo, refs, prefix="refs")

def show_ref(repo, refs, with_hash=True, prefix=""):
    if prefix:
        prefix = prefix + '/'
    for k, v in refs.items():
        if type(v) == str and with_hash:
            print (f"{v} {prefix}{k}")
        elif type(v) == str:
            print (f"{prefix}{k}")
        else:
            show_ref(repo, v, with_hash=with_hash, prefix=f"{prefix}{k}")

class GitTag(GitCommit):
    """_summary_

    Args:
        GitCommit (_type_): _description_
    """
    fmt = b'tag'

argsp = argsubparsers.add_parser("tag",
                                 help="List and create tags")
argsp.add_argument("-a",
                   action="store_true",
                   dest="create_tag_object",
                   help="whether to create a tag object")
argsp.add_argument("name",
                   nargs="?",
                   help="the new tag name")
argsp.add_argument("object",
                   default="HEAD",
                   nargs="?",
                   help="The object the new tag will point to")
def cmd_tag(args):
    repo = repo_find()

    if args.name:
        tag_create(repo,
                   args.name,
                   args.object,
                   create_tag_object = args.create_tag_object)
    else:
        refs = ref_list(repo)
        show_ref(repo, refs["tags"], with_hash=False)

def tag_create(repo, name, ref, create_tag_object):
    """_summary_

    Args:
        repo (_type_): _description_
        name (_type_): _description_
        ref (_type_): _description_
        create_tag_object (_type_): _description_
    """

    sha = object_find(repo, ref)
    #get the GitObject from the object reference

    if create_tag_object:
        #create tag object (commit)
        tag = GitTag()
        tag,kvlm = dict()
        tag,kvlm[b'object'] = sha.encode()
        tag.kvlm[b'type'] = b'commit'
        tag.kvlm[b'tag'] = name.encode()
        # feel fre to let the user give their name
        #notice you can fix this after commit, read on!
        tag.kvlm[b'tagger'] = b'Chronos <chronos@example.com'
        #...and tag a message
        tag.kvlm[None] = b"A tag generated by Chronos, which won't let you customize the message"
        tag_sha = object_write(tag, repo)
        #create a ref
        ref_create(repo, "tags/" + name, tag_sha)

    else:
        #create a ligthwheith tag (ref)
        ref_create(repo, "tags/" + name, sha)

def ref_create(repo, ref_name, sha):
    """_summary_

    Args:
        repo (_type_): _description_
        ref_name (_type_): _description_
        sha (_type_): _description_
    """
    with open(repo_file(repo, "refs/" + ref_name), 'w') as fp:
        fp.write(sha + "\n")

def object_resolve(repo, name):
    """resolve name to an object hash in repo

    this function is aware of:

    - The HEAD literal
    - short and long hashses
    - tags
    - branches
    - remote branches
    """
    candidates = list()
    hashRE = re.compile(r"^[0-9A-Fa-f]{4,40}$")

    #empy string? abort this shit
    if not name.strip():
        return None
    
    # Head is nonambiguous
    if name == "HEAD":
        return [ ref_resolve(repo, "HEAD") ]
    
    # if it is a hex string (shit), try for a hash
    if hashRE.match(name):
        #this may be a hash, either small or full. 4 seems to be the minimal
        # len for git to consider something a short hash
        # this limit is documented in man git-rev-parse
        # já tá tudo ná mão, só temos que transformar o hex em uma hash agora
        name = name.lower()
        prefix = name[0:2]
        path = repo_dir(repo, "objects", prefix, mkdir=False)
        if path:
            rem = name[2:]
            for f in os.listdir(path):
                if f.startswith(rem):
                    # notice a string startswith() itself, so this work for full hashes
                    candidates.append(prefix + f)

    #try for references
    as_tag = ref_resolve(repo, "refs/tags" + name)
    if as_tag: #did it find a tag??
        candidates.append(as_tag)

    as_branch = ref_resolve(repo, "refs/heads" + name)
    if as_branch: #it is a branch??
        candidates.append(as_branch)

    as_remote_branch = ref_resolve(repo, "refs/remotes" + name)
    if as_remote_branch: # did we find a remote branch??
        candidates.append(as_remote_branch)

    return candidates

argsp = argsubparsers.add_parser("rev-parse",
                                 help="Parse revision (or other objects) identifiers")
argsp.add_argument("--chronos-type",
                   metavar="type",
                   dest="type",
                   choices=["blob", "commit", "tag", "tree"],
                   default=None,
                   help="Specify the expected type")
argsp.add_argument("name",
                   help="The name to parse")

def cmd_rev_parse(args):
    if args.type:
        fmt = args;type.encode()

    else:
        fmt = None

    repo = repo_find()

    print (object_find(repo, args.name, fmt, follow=True))

class GitIndexEntry (object):
    def __init__(self, ctime=None, mtime=None, dev=None, ino=None, mode_type=None,
                mode_perms=None, uid=None, gid=None, fsize=None, sha=None, flag_assume_valid=None, 
                flag_stage=None, name=None):

        # The last time a file metadata changed. This is a pair (timestamp in seconds, nanosecs)
        self.ctime = ctime
        #the last file in data changed. this i s a pair (timestamp in seconds, nanosecs)
        self.mtime = mtime
        #the ID of the device containing this file
        self.dev = dev
        #the file inode number
        self.ino = ino
        #the obj type, either b1000 (regular), b1010 (symlink), b111- (gitlink)
        self.mode_type = mode_type
        #the obj permission, an integer
        self.mode_perms = mode_perms
        #uder uid
        self.uid = uid
        #group id of owner
        self.gid = gid
        #size of obj, in bytes
        self.fsize = fsize
        #obj sha
        self.sha = sha
        self.flag_assume_valid = flag_assume_valid
        self.flag_stage = flag_stage
        #name of the obj (full path)
        self.name = name

class GitIndex (object):
    version = None
    entries = []
    #exit = None
    #sha = none

    def __init__(self, version=2, entries=None):
        if not entries:
            entries = list()

        self.version = version
        self.entries = entries

def index_read(repo):
    index_file = repo_file(repo, "index")

    #new repo have no index
    if not os.path.exists(index_file):
        return GitIndex()

    with open(index_file, 'rb') as f:
        raw = f.read()

    header = raw[:12]
    signature = header[:4]
    assert signature == b"DIRC" #DirCache
    version = int.from_bytes(header[4:8], "big")
    assert version == 2, "Chronos only support index version 2"
    count = int.from_bytes(header[8:12], "big")

    entries = list()

    content = raw[12:]

    idx = 0
    for i in range(0, count):
        # read creation time, as a unix timestamp (seconds since the epoch)
        ctime_s = int.from_bytes(content[idx: idx+4], "big")
        #read creation time, as nanosecs after timestamps, for extra precision
        ctime_ns = int.from_bytes(content[idx+4: idx+8], "big")
        #tsame for modification time
        mtime_s = int.from_bytes(content[idx+8: idx+12], "big")
        #nanosecs
        mtime_ns = int.from_bytes(content[idx+12: idx+16], "big")
        #device id
        dev = int.from_bytes(content[idx+16: idx+20], "big")
        # inode
        ino = int.from_bytes(content[idx+20: idx+24], "big")
        #ignored
        unused = int.from_bytes(content[idx+24: idx+26], "big")
        assert 0 == unused
        mode = int.from_bytes(content[idx+26: idx+28], "big")
        mode_type = mode >> 12
        assert mode_type in [0b1000, 0b1010, 0b1110]
        mode_perms = mode & 0b0000000111111111
        #user id
        uid = int.from_bytes(content[idx+28: idx+32], "big")
        # group id
        gid = int.from_bytes(content[idx+32: idx+36], "big")
        #size
        fsize = int.from_bytes(content[idx+36: idx+40], "big")
        #sha (obj id) we will store it as a lowercase hex string for consistensy
        sha = format(int.from_bytes(content[idx+40: idx+60], "big"), "040x")
        #flags to ignore
        flags = int.from_bytes(content[idx+60: idx+62], "big")
        flag_assume_valid = (flags & 0b1000000000000000) != 0
        flag_extended = (flags & 0b0100000000000000) != 0
        assert not flag_extended
        flag_stage =  flags & 0b0011000000000000

        #len of the name, stored in 12 bits, some max value is 0xFFF, 4095
        name_length = flags & 0b0000111111111111

        # we have read 62 bytes so far

        idx += 62

        if name_length < 0xFFF:
            assert content[idx + name_length] == 0x00
            raw_name = content[idx:idx+name_length]
            idx += name_length + 1

        else:
            print(f"Notice: name is 0x{name_length:X} bytes long!")
            #have to test it more
            null_idx = content.find(b'\x00', idx+ 0xFFF)
            raw_name = content[idx: null_idx]
            idx = null_idx + 1

        #paerse the name as utf8
        name = raw_name.decode("utf8")

        #data is padded on multiple bytes for pointer alignment

        idx = 8 * ceil(idx / 8)

        #and we add this entry to our list
        entries.append(GitIndexEntry(ctime=(ctime_s, ctime_ns),
                                    mtime=(mtime_s, mtime_ns),
                                    dev=dev,
                                    ino=ino,
                                    mode_type=mode_type,
                                    mode_perms=mode_perms,
                                    uid=uid,
                                    gid=gid,
                                    fsize=fsize,
                                    sha=sha,
                                    flag_assume_valid=flag_assume_valid,
                                    flag_stage=flag_stage,
                                    name=name))

    return GitIndex(version=version, entries=entries)

argsp = argsubparsers.add_parser("ls-files", help="List of all stage files")
argsp.add_argument("--verbose", action="store_true", help="Show everything in the staging files.")

def cmd_ls_files(args):
    repo = repo_find()
    index = index_read(repo)
    if args.verbose:
        print(f"Index file format v{index.version}, containing {len(index.entries)} entries")

    for e in index.entries:
        print(e.name)
        if args.verbose:
            entry_type = {  0b1000: "regular file",
                            0b1010: "symlink",
                            0b1110: "git link"  }[e.mode_type]

            print(f"    {entry_type} with perms: {e.mode_perms:o}")
            print(f"  on blob: {e.sha}")
            print(f"  created: {datetime.fromtimestamp(e.ctime[0])}.{e.ctime[1]}, modified: {datetime.fromtimestamp(e.mtime[0])}.{e.mtime[1]}")
            print(f"  device: {e.dev}, inode: {e.ino}")
            print(f"  user: {pwd.getpwuid(e.uid).pw_name} ({e.uid})  group: {grp.getgrgid(e.gid).gr_name} ({e.gid})")
            print(f"  flags: stage={e.flag_stage} assume_valid={e.flag_assume_valid}")

argsp = argsubparsers.add_parser("check-ignore", help = "Check path against ignore rules.")
argsp.add_argument("path", nargs="+", help="Paths to check")

def cmd_check_ignore(args):
    repo = repo_find()
    rules = gitignore_read(repo)
    for path in args.path:
        if check_ignore(rules, path):
            print(path)


def gitignore_parse1(raw):
    raw = raw.strip()

    if not raw or raw[0] == "#":
        return None
        
    elif raw[0] == "!":
        return (raw[1:], False)
    else:
        return (raw, True)

def gitignore_parse(lines):
    ret = list()

    for line in lines:
        parsed = gitignore_parse1(line)
        if parsed:
            ret.append(parsed)

    return ret

class GitIgnore(object):
    absolute = None
    scoped = None

    def __init__(self, absolute, scoped):
        self.absolute = absolute
        self.scoped = scoped

def gitignore_read(repo):
    ret = GitIgnore(absolute=list(), scoped=dict())

    #read local config in .git/info/exclude
    repo_file = os.path.join(repo.gitdir, "info/exclude")
    if os.path.exists(repo_file):
        with open(repo_file, "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))

    #global config
    if "XDG_CONFIG_HOME" in os.environ:
        config_home = os.environ["XDG_CONFIG_HOME"]
    else:
        config_home = os.path.expanduser("~/.config")
    global_file = os.path.join(config_home, "git/ignore")

    if os.path.exists(global_file):
        with open(global_file, "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))

    #.gitignore files in the index
    index = index_read(repo)

    for entry in index.entries:
        if entry.name == ".gitignore" or entry.name.endswith("/.gitignore"):
            dir_name = os.path.dirname(entry.name)
            contents = object_read(repo, entry.sha)
            lines = contents.blobdata.decode("utf8").splitlines()
            ret.scoped[dir_name] = gitignore_parse(lines)
    return ret

def check_ignore1(rules, path):
    result = None
    for (pattern, value) in rules:
        if fnmatch(path, pattern):
            result = value
    return result

def check_ignore_scoped(rules, path):
    parent = os.path.dirname(path)
    while True:
        if parent in rules:
            result = check_ignore1(rules[parent], path)
            if result != None:
                return result
        if parent == "":
            break
        parent = os.path.dirname(parent)
    return None

def check_ignore_absolute(rules, path):
    parent = os.path.dirname(path)
    for ruleset in rules:
        result = check_ignore1(ruleset, path)
        if result != None:
            return result
    return False #this is a reasonable default at this point

# join all then
def check_ignore(rules, path):
    if os.path.isabs(path):
        raise Exception("This Function requires a path to be relative to the repository's root")

    result = check_ignore_scoped(rules.scoped, path)
    if result != None:
        return result

    return check_ignore_absolute(rules.absolute, path)

argsp = argsubparsers.add_parser("status", help = "Show the working tree status")

def cmd_status(_):
    repo = repo_find()
    index = index_read(repo)

    cmd_status_branch(repo)
    cmd_status_head_index(repo, index)
    print()
    cmd_status_index_worktree(repo, index)

def branch_get_active(repo):
    with open(repo_file(repo, "HEAD"), "r") as f:
        head = f.read()

    if head.startswith("ref: refs/heads/"):
        return(head[16:-1])
    else:
        return False

def cmd_status_branch(repo):
    branch = branch_get_active(repo)
    if branch:
        print(f"On branch {branch}.")
    else:
        print(f"HEAD detached at {object_find(repo, 'HEAD')}")

def tree_to_dict(repo, ref, prefix=""):
    ret = dict()
    tree_sha = object_find(repo, ref, fmt=b"tree")
    tree = object_read(repo, tree_sha)

    for leaf in tree.items:
        full_path = os.path.join(prefix, leaf.path)

        is_subtree = leaf.mode.startswith(b'04')

        # we read the object to extract its type (this is uselessly expensive: we could just open it as a file and read the first few bytes)
        if is_subtree:
            ret.update(tree_to_dict(repo, leaf.sha, full_path))
        else:
            ret[full_path] = leaf.sha

    return ret

def cmd_status_head_index(repo, index):
    print("Changes to be committed:")

    head = tree_to_dict(repo, "HEAD")
    for entry in index.entries:
        if entry.name in head:
            if head[entry.name] != entry.sha:
                print("    Modified:", entry.name)
            del head[entry.name] #del the key
        else:
            print("     Added:      ", entry.name)

    # key still in HEAD are files that we haven't met in the index, and thus have been deleted
    for entry in head.keys():
        print("     Deleted:  ", entry)

def cmd_status_index_worktree(repo, index):
    print("Changes not staged for commit:")

    ignore = gitignore_read(repo)

    gitdir_prefix = repo.gitdir + os.path.sep

    all_files = list()

    # We begin by wlking the filesystem
    for (root, _, files) in os.walk(repo.worktree, True):
        if root==repo.gitdir or root.startswith(gitdir_prefix):
            continue
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path;rel_path(full_path, repo.worktree)
            all_files.append(rel_path)

    # now traverse the index, and compare real files with the cached versions

    for entry in index.entries:
        full_path = os.path.join(repo.worktree, entry.name)

        #that file "name" is in the index

        if not os.path.exists(full_path):
            print("     Deleted:  ", entry.name)
        else:
            stat = os.stat(full_path)

            #compare metadata
            ctime_ns = entry.ctime[0] * 10**9 + entry.ctime[1]
            mtime_ns = entry.mtime[0] * 10**9 + entry.mtime[1]
            if (stat.st_ctime_ns != ctime_ns) or (stat.st_mtime_ns != mtime_ns):
                # if different, compare
                with open(full_path, "rb") as fd:
                    new_sha = object_hash(fd, b"blob", None)
                    # if the hashes are the same, the files are the same
                    same = entry.sha == new_sha

                    if not same:
                        print("     Modified:  ", entry.name)

        if entry.name in all_files:
            all_files.remove(entry.name)

    print()
    print("Untracked files:")

    for f in all_files:
        # if a full directory is untracked, it should display its name without its contents

        if not check_ignore(ignore, f):
            print(" ", f)

def index_write(repo, index):
    with open(repo_file(repo, "index"), "wb") as f:

        #header
        #write the bytes
        f.write(b"DIRC")
        #write version number
        f.write(index.version.to_bytes(4, "big"))
        #the number of entries
        f.write(len(index.entries).to_bytes(4, "big"))

        #entries

        idx = 0
        for e in index.entries:
            f.write(e.ctime[0].to_bytes(4, "big"))
            f.write(e.ctime[1].to_bytes(4, "big"))
            f.write(e.mtime[0].to_bytes(4, "big"))
            f.write(e.mtime[1].to_bytes(4, "big"))
            f.write(e.dev.to_bytes(4, "big"))
            f.write(e.ino.to_bytes(4, "big"))

            #mode

            mode = (e.mode_type << 12) | e.mode_perms
            f.write(mode.to_bytes(4, "big"))

            f.write(e.uid.to_bytes(4, "big"))
            f.write(e.gid.to_bytes(4, "big"))

            f.write(e.fsize.to_bytes(4, "big"))
            # Convert to int.
            f.write(int(e.sha, 16).to_bytes(20, "big"))

            flag_assume_valid = 0x1 << 15 if e.flag_assume_valid else 0

            name_bytes = e.name.encode("utf8")
            bytes_len = len(name_bytes)
            if bytes_len >= 0xFFF:
                name_length = 0xFFF
            else:
                name_length = bytes_len

            # We merge back three pieces of data
            f.write((flag_assume_valid | e.flag_stage | name_length).to_bytes(2, "big"))

            # Write back the name, and a final 0x00.
            f.write(name_bytes)
            f.write((0).to_bytes(1, "big"))

            idx += 62 + len(name_bytes) + 1

            # Add padding
            if idx % 8 != 0:
                pad = 8 - (idx % 8)
                f.write((0).to_bytes(pad, "big"))
                idx += pad


argsp = argsubparsers.add_parser("rm", help="Remove files from the working tree and the index")
argsp.add_argument("path", nargs="+", help="Files to remove")

def cmd_rm(args):
    repo = repo_find
    rm(repo, args.path)

def rm(repo, paths, delete=True, skip_missing=False):
    #find & read index

    index = index_read(repo)
    worktree = repo.worktree + os.sep

    #male paths absolut

    abspaths = set()
    for path in paths:
        abspath = os.path.abspath(path)
        if abspath.startswith(worktree):
            abspaths.add(abspath)
        else:
            raise Exception(f"Cannot remove paths outside of worktree: {paths}")

    #list of entries to keep, which will be write to indes
    kept_entries = list()

    #list of removed paths
    remove = list()

    #iterate over the list of entries
    for e in index.entries:
        full_path = os.path.join(repo.worktree, e.name)

        if full_path in abspaths:
            remove.append(full_path)
            abspaths.remove(full_path)
        else:
            kept_entries.append(e)

    if len(abspaths) > 0 and not skip_missing:
        raise Exception(f"Cannot remove paths not in the index: {abspaths}")

    #  delete paths
    if delete:
        for path in remove:
            os.unlink(path)

    # Update the list of entries in the index, and write it back.
    index.entries = kept_entries
    index_write(repo, index)

argsp = argsubparsers.add_parser("add", help="Add file contents to the index")
argsp.add_argument("path", nargs="+", help='Files to add')

def cmd_add(args):
    repo = repo_find()
    add(repo, args.path)

def add(repo, paths, delete=True, skip_missing=False):

    rm (repo, paths, delete=False, skip_missing=True)

    worktree = repo.worktree + os.sep

    # Convert the paths to pairs: (absolute, relative_to_worktree)
    clean_paths = set()
    for path in paths:
        abspath = os.path.abspath(path)
        if not (abspath.startswith(worktree) and os.path.isfile(abspath)):
            raise Exception(f"Not a file, or outside the worktree: {paths}")
        relpath = os.path.relpath(abspath, repo.worktree)
        clean_paths.add((abspath,  relpath))

    index = index_read(repo)

    for (abspath, relpath) in clean_paths:
        with open(abspath, "rb") as fd:
            sha = object_hash(fd, b"blob", repo)

            stat = os.stat(abspath)

            ctime_s = int(stat.st_ctime)
            ctime_ns = stat.st_ctime_ns % 10**9
            mtime_s = int(stat.st_mtime)
            mtime_ns = stat.st_mtime_ns % 10**9

            entry = GitIndexEntry(ctime=(ctime_s, ctime_ns), mtime=(mtime_s, mtime_ns), dev=stat.st_dev, ino=stat.st_ino,
                                  mode_type=0b1000, mode_perms=0o644, uid=stat.st_uid, gid=stat.st_gid,
                                  fsize=stat.st_size, sha=sha, flag_assume_valid=False,
                                  flag_stage=False, name=relpath)
            index.entries.append(entry)

    # Write the index back
    index_write(repo, index)

argsp = argsubparsers.add_parser("commit", help="Record changes to the repository")
argsp.add_argument("-m", 
                    metavar="message",
                    dest="message",
                    help="Message to link with this commit")

def gitconfig_read():
    xdg_config_home = os.environ["XDG_CONFIG_HOME"] if "XDG_CONFIG_HOME" in os.environ else "~/.config"
    configfiles = [
        os.path.expanduser(os.path.join(xdg_config_home, "git/config")),
        os.path.expanduser("~/.gitconfig")
    ]

    config = configparser.ConfigParser()
    config.read(configfiles)
    return config

def gitconfig_user_get(config):
    if "user" in config:
        if "name" in config["user"] and "email" in config["user"]:
            return f"{config['user']['name']} <{config['user']['email']}>"
    return None

def tree_from_index(repo, index):
    contents = dict()
    contents[""] = list()

    for entry in index.entries:
        dirname = os.path.dirname(entry.name)

        key = dirname
        while key != "":
            if not key in contents:
                contents[key] = list()
            key = os.path.dirname(key)

        # For now, simply store the entry in the list.
        contents[dirname].append(entry)

    sorted_paths = sorted(contents.keys(), key=len, reverse=True)

    sha = None

    # We ge through the sorted list of paths (dict keys)
    for path in sorted_paths:
        # Prepare a new, empty tree object
        tree = GitTree()

        # Add each entry to our new tree, in turn
        for entry in contents[path]:
            if isinstance(entry, GitIndexEntry): # Regular entry (a file)

                leaf_mode = f"{entry.mode_type:02o}{entry.mode_perms:04o}".encode("ascii")
                leaf = GitTreeLeaf(mode = leaf_mode, path=os.path.basename(entry.name), sha=entry.sha)
            else: # Tree. stored it as a pair: (basename, SHA)
                leaf = GitTreeLeaf(mode = b"040000", path=entry[0], sha=entry[1])

            tree.items.append(leaf)

        # Write the new tree object to the store.
        sha = object_write(tree, repo)

        parent = os.path.dirname(path)
        base = os.path.basename(path) # The name without the path, eg main.go for src/main.go
        contents[parent].append((base, sha))

    return sha

def commit_create(repo, tree, parent, author, timestamp, message):
    commit = GitCommit() # Create the new commit object.
    commit.kvlm[b"tree"] = tree.encode("ascii")
    if parent:
        commit.kvlm[b"parent"] = parent.encode("ascii")

    # Trim message and add a trailing \n
    message = message.strip() + "\n"
    # Format timezone
    offset = int(timestamp.astimezone().utcoffset().total_seconds())
    hours = offset // 3600
    minutes = (offset % 3600) // 60
    tz = "{}{:02}{:02}".format("+" if offset > 0 else "-", hours, minutes)

    author = author + timestamp.strftime(" %s ") + tz

    commit.kvlm[b"author"] = author.encode("utf8")
    commit.kvlm[b"committer"] = author.encode("utf8")
    commit.kvlm[None] = message.encode("utf8")

    return object_write(commit, repo)

def cmd_commit(args):
    repo = repo_find()
    index = index_read(repo)
    # Create trees, grab back SHA for the root tree.
    tree = tree_from_index(repo, index)

    # Create the commit object itself
    commit = commit_create(repo,
                           tree,
                           object_find(repo, "HEAD"),
                           gitconfig_user_get(gitconfig_read()),
                           datetime.now(),
                           args.message)

    # Update HEAD so the commit is now the tip of the active branch.
    active_branch = branch_get_active(repo)
    if active_branch: # If we're on a branch, update refs/heads/BRANCH
        with open(repo_file(repo, os.path.join("refs/heads", active_branch)), "w") as fd:
            fd.write(commit + "\n")
    else: # Otherwise, update HEAD itself.
        with open(repo_file(repo, "HEAD"), "w") as fd:
            fd.write("\n")
