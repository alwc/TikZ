from batch import BatchIterator
from language import *
from render import render

import matplotlib.pyplot as plot
import sys
import numpy as np
import tensorflow as tf
import os
from PIL import Image
import pickle

learning_rate = 0.001

def loadImages(filenames):
    def processPicture(p):
        p = p.convert('L')
        (w,h) = p.size
        return 1.0 - np.array(list(p.getdata())).reshape((h,w))/255.0
    return [ processPicture(Image.open(n)) for n in filenames ]

def showImage(image):
    plot.imshow(image,cmap = 'gray')
    plot.show()

def loadPrograms(filenames):
    return [ pickle.load(open(n,'rb')) for n in filenames ]

def loadExamples(numberOfExamples, filePrefix):
    programs = loadPrograms([ "%s-%d.p"%(filePrefix,j)
                              for j in range(numberOfExamples) ])
    startingExamples = []
    endingExamples = []
    target = [[],[],[],[]]


    # get one example from each line of each program
    for j,program in enumerate(programs):
        trace = loadImages([ "%s-%d-%d.png"%(filePrefix, j, k) for k in range(len(program)) ])
        targetImage = trace[-1]
        currentImage = np.zeros(targetImage.shape)
        for k,l in enumerate(program.lines):
            startingExamples.append(currentImage)
            endingExamples.append(targetImage)
            currentImage = trace[k]
            if isinstance(l,Circle):
                x,y = l.center.x,l.center.y
                target[0].append(x)
                target[1].append(y)
                target[2].append(0)
                target[3].append(0)
            elif isinstance(l,Line):
                target[0].append(l.points[0].x)
                target[1].append(l.points[0].y)
                target[2].append(l.points[1].x)
                target[3].append(l.points[1].y)
            else:
                raise Exception('Unhandled line:'+str(l))
            
    targetVectors = [np.array(t) for t in target ]
    
    return np.array(startingExamples), np.array(endingExamples), targetVectors

# we output 4 categorical distributions over ten choices
OUTPUTDIMENSIONS = [10,10,10,10]

class RecognitionModel():
    def __init__(self):
        self.inputPlaceholder = tf.placeholder(tf.float32, [None, 300, 300, 2])
        # what is the target category?
        self.targetPlaceholder = [ tf.placeholder(tf.int32, [None]) for _ in OUTPUTDIMENSIONS ]
        # do we actually care about the prediction made?
        #self.targetMaskPlaceholder = [ tf.placeholder(tf.float32, [None]) for _ in OUTPUTDIMENSIONS ]

        numberOfFilters = [5]
        c1 = tf.layers.conv2d(inputs = self.inputPlaceholder,
                              filters = numberOfFilters[0],
                              kernel_size = [10,10],
                              padding = "same",
                              activation = tf.nn.relu,
                              strides = 10)

        f1 = tf.reshape(c1, [-1, 900*numberOfFilters[-1]])

        self.prediction = [ tf.layers.dense(f1, dimension, activation = None) for dimension in OUTPUTDIMENSIONS ]

        self.hard = [ tf.cast(tf.argmax(p,dimension = 1),tf.int32) for p in self.prediction ]

        self.averageAccuracy = reduce(tf.logical_and,
                                      [tf.equal(h,t) for h,t in zip(self.hard,self.targetPlaceholder)])
        self.averageAccuracy = tf.reduce_mean(tf.cast(self.averageAccuracy, tf.float32))

        self.loss = sum([ tf.reduce_sum(tf.nn.sparse_softmax_cross_entropy_with_logits(labels = t,logits = p))
                          for t,p in zip(self.targetPlaceholder, self.prediction) ])

        self.optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(self.loss)

    def train(self, numberOfExamples, exampleType, checkpoint = "/tmp/model.checkpoint"):
        partialImages,targetImages,targetVectors = loadExamples(numberOfExamples,
                                                                "syntheticTrainingData/"+exampleType)
        images = np.stack([partialImages,targetImages],3)

        initializer = tf.global_variables_initializer()
        iterator = BatchIterator(50,tuple([images] + targetVectors))
        saver = tf.train.Saver()

        with tf.Session() as s:
            s.run(initializer)
            for i in range(1000):
                batchData = iterator.next()
                feed = {self.inputPlaceholder: batchData[0]}
                for placeholder,vector in zip(self.targetPlaceholder,batchData[1:]):
                    feed[placeholder] = vector
                
                _,l,accuracy = s.run([self.optimizer, self.loss, self.averageAccuracy],
                                     feed_dict = feed)
                if i%50 == 0:
                    print i,accuracy,l
                if i%100 == 0:
                    print "Saving checkpoint: %s" % saver.save(s, checkpoint)

    def test(self, numberOfExamples, exampleType, checkpoint = "/tmp/model.checkpoint"):
        partialImages,targetImages,targetVectors = loadExamples(numberOfExamples,
                                                                "syntheticTrainingData/"+exampleType)
        images = np.stack([partialImages,targetImages],3)

        saver = tf.train.Saver()
        with tf.Session() as s:
            saver.restore(s,checkpoint)
            feed = {self.inputPlaceholder:images}
            for placeholder,vector in zip(self.targetPlaceholder,targetVectors):
                feed[placeholder] = vector
            outputs = s.run([self.averageAccuracy] + self.hard,
                                   feed_dict = feed)
            accuracy = outputs[0]
            predictions = outputs[1:]
            print "Average accuracy:",accuracy
            for j in range(5):
                showImage(partialImages[j])
                showImage(targetImages[j])
                print [ predictions[d][j] for d in range(len(OUTPUTDIMENSIONS)) ]
                print [ targetVectors[d][j] for d in range(len(OUTPUTDIMENSIONS)) ]
                print ""

    def draw(self, targetImages, checkpoint = "/tmp/model.checkpoint"):
        targetImages = [np.reshape(i,(1,300,300)) for i in loadImages(targetImages) ]
        saver = tf.train.Saver()
        with tf.Session() as s:
            saver.restore(s,checkpoint)

            for targetImage in targetImages:
                showImage(targetImage[0])

                currentImage = np.zeros(targetImage.shape)
                
                currentProgram = []

                while True:
                    feed = {self.inputPlaceholder:np.stack([currentImage,targetImage],3)}
                    hardDecisions = s.run(self.hard,
                                          feed_dict = feed)

                    if hardDecisions[2] == 0 and hardDecisions[3] == 0:
                        currentProgram.append(Circle(AbsolutePoint(hardDecisions[0], hardDecisions[1]),1))
                    else:
                        currentProgram.append(Line([AbsolutePoint(hardDecisions[0], hardDecisions[1]),
                                                    AbsolutePoint(hardDecisions[2], hardDecisions[3])]))

                    p = str(Sequence(currentProgram))
                    print p,"\n"
                    currentImage = 1.0 - render([p],yieldsPixels = True)[0]
                    currentImage = np.reshape(currentImage, targetImage.shape)
                    showImage(currentImage[0])

                    if len(currentProgram) > 2:
                        break
                    

if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'test':
#        RecognitionModel().test(100, "doubleCircleLine")
        RecognitionModel().draw(["syntheticTrainingData/doubleCircleLine-0-2.png"])
    else:
        RecognitionModel().train(100, "doubleCircleLine")
