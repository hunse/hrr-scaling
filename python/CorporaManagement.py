import sys  
import cPickle as pickle
from VectorOperations import *
from SymbolDefinitions import *
import random
import Queue

class CorpusHandler:
    #D = 512 # number of dimensions per vocab vector
    corpusDict = None
    cleanupMemory = None
    knowledgeBase = None
    
    def __init__(self, try_load, D=512, input_dir="."):
      self.try_load = try_load
      self.D = D
      self.input_dir = input_dir

    def parseWordnet(self):
        if self.try_load and self.loadCorpusDict(self.input_dir+'/cd1.data'):
          return

        fileposmap = {self.input_dir+'/data.noun': 'n', self.input_dir+'/data.verb': 'v', self.input_dir+'/data.adj' : 'a', self.input_dir+'/data.adv' : 'r'}
        if self.corpusDict is not None:
            print "Warning: overwriting existing corpus dictionary."

        self.corpusDict = {}

        # See http://wordnet.princeton.edu/wordnet/man/wndb.5WN.html
        # and http://wordnet.princeton.edu/wordnet/man/wninput.5WN.html
        # for more information about what's going on here (parsing files).
        for filename in fileposmap:
            with open(filename,'rb') as f:
                pos = fileposmap[filename]
                self.skipNotice(f)

                line = f.readline()
                while line:
                    parse = line.split()
                    tag = (pos, int(parse[0])) # this tag uniquely identifies a synset (word sense)
                    self.corpusDict[tag] = []
                    w_cnt = int(parse[3], 16)
                    p_i = 4+w_cnt*2
                    p_cnt = int(parse[p_i])
                    
                    for i in range(p_cnt):
                        ptr = parse[p_i+1]
                        offset = int(parse[p_i+2])
                        ss_type = parse[p_i+3]
                        if ss_type == 's': ss_type = 'a' # adjective Satellites are just Adjectives
                        pointerTag = (ss_type, offset)
                        self.corpusDict[tag].append((ptr, pointerTag))
                        # ignoring parse[p_i+4] (word/word mappings)
                        p_i = p_i + 4
                        
                    line = f.readline()

    def createCorpusSubset(self, proportion, seed=1):
      subset_dict = {}
      
      random.seed(seed)
  
      #randomly pick a starting point, following all links from that node,
      # do the same recursively for each node we just added. 
      # once we have enough nodes, have to go back through and correct 
      # the keys so they point to the right place...maybe...actually we don't even have to do that, since its just done with keys.

      #just have to make sure we remove all the dangling links...so once we've determined that we have enough nodes, have to go through
      # all the nodes we have added to the graph but have yet to recurse on and delete all the links they have which link to something which isn't
      # in the subset
      proportion = max(0.0,min(1.0, proportion))

      size = 0
      target_size = proportion * len(self.corpusDict)

      queue = Queue.Queue()

      while size < target_size:
        if queue.empty():
          queue.put( random.choice(self.corpusDict.keys()))

        next_entry = queue.get()

        if next_entry in subset_dict:
          continue

        subset_dict[next_entry] = self.corpusDict[next_entry]
        new_entries = self.corpusDict[next_entry]
        size=size+1

        for item in new_entries:
          queue.put(item[1])
      
      for key in subset_dict:
        removal_list = []

        for item in subset_dict[key]:
          if item[1] not in subset_dict:
            removal_list.append(item)

        for item in removal_list:
          subset_dict[key].remove(item)

      self.corpusDict = subset_dict
      #print >> sys.stderr, "Corpora size: ", subset_dict
      
      #print [all([(i[1] in subset_dict) for i in subset_dict[x]]) for x in subset_dict]
      

    def saveCorpusDict(self, filename):
        if self.corpusDict is None:
            raise Exception("Attempted to save corpus dictionary before it was created.")
        
        with open(filename, 'w') as cfile:
            pickle.dump(self.corpusDict, cfile)

    def loadCorpusDict(self, filename):
      try:
        with open(filename, 'r') as cfile:
            self.corpusDict = pickle.load(cfile)
        print "Loaded corpus dict"
        return True
      except:
        return False

    def processCorpus(self):
        '''Remove excessive relationships, handle circularity, etc.'''
        processed = set()
        stack = []
        lastHolonym = None
        for item in self.corpusDict:
            if item in processed: continue

            activeItem = item
            localStack = []
            localProcessed = set()

            while activeItem is not None:
                # find all relations of current item
                if activeItem not in localProcessed:
                    for relation in self.corpusDict[activeItem]:
                        if relation[0] in vocab_symbols:
                            localStack.append(relation)
                            localProcessed.add(activeItem)

                # select an item and update stack (for branching trees)
                activeRelation = None
                if len(localStack) > 1:
                    activeRelation = localStack.pop()
                    stack.append((activeItem, localProcessed.copy(), lastHolonym, localStack))
                    localStack = []
                elif len(localStack) == 1:
                    activeRelation = localStack[0]
                    localStack = []
                elif len(stack) > 0:
                    processed.update(localProcessed)
                    activeItem, localProcessed, lastHolonym, localStack = stack.pop()
                else:
                    activeItem = None

                # check whether the link completes a circle
                if activeRelation is not None:
                    if activeRelation[0] in holonym_symbols:
                        lastHolonym = (activeItem, activeRelation)
                    if activeRelation[1] in localProcessed:
                        # delete a relation if a circular definition was found
                        if lastHolonym is not None:
                            self.corpusDict[lastHolonym[0]].remove(lastHolonym[1])
                            print 'deleting', lastHolonym[1], 'from', lastHolonym[1]
                            lastHolonym = None
                        else:
                            self.corpusDict[activeItem].remove(activeRelation)
                            print 'deleting', activeRelation, 'from', activeItem
                    elif activeRelation[1] not in processed:
                        activeItem = activeRelation[1]
                    else:
                        localStack = []

        processed.update(localProcessed)
        
    def generateRandomCleanup(self, useUnitary=False):
        if useUnitary:
            generatorFunc = genUnitaryVec
        else:
            generatorFunc = genVec
        
        self.cleanupMemory = {}
        for key in self.corpusDict.keys():
            self.cleanupMemory[key] = generatorFunc(self.D)

        # Add relationship and POS keywords to the cleanup memory
        for symbol in vocab_symbols:
            self.cleanupMemory[symbol] = generatorFunc(self.D)

    def formKnowledgeBase(self, identityCleanup=False, useUnitary=False):
        # Check existence of corpus
        if self.corpusDict is None:
            raise Exception("Attempted to form the knowledge base without a corpus.")
        
        print "Length!", len(self.corpusDict)
    
        # Check existence of cleanup memory, generate if required
        if self.cleanupMemory is None:
          if not (self.try_load and self.loadCleanup(self.input_dir+'/clean1.data')) :
          #if not (self.try_load and self.loadCleanup('clean1.data') and len(self.cleanupMemory) == len(self.corpusDict)):
              print "Generating random cleanup"
              self.generateRandomCleanup(useUnitary)

        if self.try_load and self.loadKnowledgeBase(self.input_dir+'/kb1.data') :
        #if self.try_load and self.loadKnowledgeBase('kb1.data') and len(self.knowledgeBase) == len(self.corpusDict):
          return

        self.knowledgeBase = {}

        # Order words by the dependencies of their definitions
        if not identityCleanup:
            keyOrder = self.corpusDict.keys()
        else:
            keyOrder = []
            stuck = False
            resolved = set(vocab_symbols)
            
            dependencies = {}
            for key in self.corpusDict.keys():
                dependencies[key] = set([tag[1] for tag in self.corpusDict[key]
                                         if tag[0] in vocab_symbols])
                    
            while len(keyOrder) < len(self.corpusDict)+len(vocab_symbols) and not stuck:
                resolvable = set()
                for key in dependencies:
                  if dependencies[key].issubset(resolved):
                        resolvable.add(key)

                # add the resolvable keys to the order list and resolved set
                keyOrder.extend(resolvable)
                resolved = resolved.union(resolvable)

                # remove resolved tags from the dependency dictionary
                for r in resolvable:
                    del dependencies[r]

                # if no items are resolvable, we're stuck
                if len(resolvable)==0:
                    stuck=True

            del resolved
            del resolvable
            if len(keyOrder) < len(self.corpusDict):
                raise Exception("Dependency resolution failed.")


        # Define the knowledge base in terms of the cleanup memory
        for symbol in vocab_symbols:
            self.knowledgeBase[symbol] = self.cleanupMemory[symbol]
        for key in keyOrder:
            self.knowledgeBase[key] = genVec(self.D)

            for relation in self.corpusDict[key]:
                if relation[0] not in vocab_symbols: continue

                if identityCleanup:
                    pair = cconv(self.knowledgeBase[relation[0]], self.knowledgeBase[relation[1]])
                else:
                    if not self.cleanupMemory.has_key(relation[0]):
                        self.cleanupMemory[relation[0]] = genVec(self.D)
                    pair = cconv(self.cleanupMemory[relation[0]], self.cleanupMemory[relation[1]])

                if self.knowledgeBase.has_key(key):
                    self.knowledgeBase[key] = self.knowledgeBase[key] + pair
                else:
                    self.knowledgeBase[key] = pair

            if identityCleanup:
                self.knowledgeBase[key] = self.knowledgeBase[key] + self.cleanupMemory[key]
            self.knowledgeBase[key] = normalize(self.knowledgeBase[key])

        if identityCleanup:
            self.cleanupMemory = self.knowledgeBase


        # Iterate a few more times to try to get 
        
    def saveCleanup(self, filename):
        if self.cleanupMemory is None:
            raise Exception("Attempted to save corpus dictionary before it was created.")
        
        with open(filename, 'w') as cfile:
            pickle.dump(self.cleanupMemory, cfile)

    def loadCleanup(self, filename):
      try:
        with open(filename, 'r') as cfile:
            self.cleanupMemory = pickle.load(cfile)
        print "Loaded cleanup"

        return True

      except:
        return False

    def saveKnowledgeBase(self, filename):
        if self.knowledgeBase is None:
            raise Exception("Attempted to save corpus dictionary before it was created.")
        
        with open(filename, 'w') as kfile:
            pickle.dump(self.knowledgeBase, kfile)

    def loadKnowledgeBase(self, filename):
      try:
        with open(filename, 'r') as kfile:
            self.knowledgeBase = pickle.load(kfile)

        print "Loaded knowledge base"
        return True

      except:
        return False

    # File parsing utilities
    def skipNotice(self, f):
        '''Seeks to the beginning of actual data in data files
        (enabling the parser to skip the copyright notice).'''
        c = f.read(1)
        while c==' ':
            f.readline()
            c = f.read(1)
        f.seek(-1, 1)