import sys, os, argparse, logging
import numpy as np
import code
import PIL
from PIL import Image
# from model.model import Model
import tensorflow as tf
import tflearn
from tflearn.layers.core import input_data, dropout, fully_connected
from tflearn.layers.conv import conv_2d, max_pool_2d
from tflearn.layers.estimator import regression

def process_args(args):
    parser = argparse.ArgumentParser(description='description')
    parser.add_argument('--phase', dest='phase',
                        type=str, default='training',
                        help=('Directory containing processed images.'))
    parser.add_argument('--batch-dir', dest='batch_dir',
                        type=str, required=True,
                        help=('path where the batches are stored'))
    parser.add_argument('--batch-size', dest='batch_size',
                        type=str, default=5,
                        help=('size of the minibatches'))
    parameters = parser.parse_args(args)
    return parameters

def length(sequence):
    used = tf.sign(tf.reduce_max(tf.abs(sequence), reduction_indices=2))
    length = tf.reduce_sum(used, reduction_indices=1)
    length = tf.cast(length, tf.int32)
    return length

def createCNNModel(network):
    network = tflearn.layers.conv.conv_2d(network, 64, 3, activation='relu') # padding???
    network = max_pool_2d(network, 2, strides=2)

    network = conv_2d(network, 128, 3, activation='relu')
    network = max_pool_2d(network, 2, strides=2)

    network = conv_2d(network, 256, 3, activation='relu')
    network = tflearn.layers.normalization.batch_normalization(network) #same as torch?

    network = conv_2d(network, 256, 3, activation='relu')
    network = max_pool_2d(network, [1,2], strides=2)

    network = conv_2d(network, 512, 3, activation='relu')
    network = tflearn.layers.normalization.batch_normalization(network) #same as torch?
    network = max_pool_2d(network, [2,1], strides=2)

    network = conv_2d(network, 512, 3, activation='relu')
    network = tflearn.layers.normalization.batch_normalization(network) #same as torch?

    return network

def createEncoderLSTM(network):
    batchsize = tf.shape(network)[0]
    network = tf.transpose(network, [1,0,2,3])
    rnncell_fw = tf.contrib.rnn.LSTMCell(256) # TODO choose parameter
    # trainable hidden state??? (postional embedding)
    fw_state = rnncell_fw.zero_state(batch_size=batchsize, dtype=tf.float32)
    rnncell_bw = tf.contrib.rnn.LSTMCell(256) # TODO choose parameter
    bw_state = rnncell_bw.zero_state(batch_size=batchsize, dtype=tf.float32)
    l = tf.TensorArray(dtype=tf.float32, size=tf.shape(network)[0])
    params = [tf.constant(0), network, l, fw_state, bw_state]
    while_condition = lambda i, network, l, fw_state, bw_state: tf.less(i, tf.shape(network)[0])
    def body(i, network, l, fw_state, bw_state):
        outputs, output_states = tf.nn.bidirectional_dynamic_rnn(rnncell_fw, rnncell_bw, network[i], initial_state_fw=fw_state,initial_state_bw=bw_state) #,dtype=tf.float32)
        fw_state, bw_state = output_states
        # scode.interact(local=locals())
        l = l.write(i, outputs)        
        return [tf.add(i, 1), network, l, fw_state, bw_state]
    i, network, l, fw_state, bw_state = tf.while_loop(while_condition, body, params)
    network = l.stack()
    network = tf.transpose(network, perm=[2,0,3,1,4])
    s = tf.shape(network)
    network = tf.reshape(network, [s[0],s[1],s[2],s[3]*s[4]])
    return network, i #

def createDecoderLSTM(network, num_classes):
    # num_classes = 200 # class variable!!!
    dim_beta = 50 # hyperparameter!!!
    dim_h = 512 # hyperparameter!!!
    num_features = network.shape[3]
    dim_o = num_features + dim_h
    batchsize = tf.shape(network)[0]
    #
    rnncell_fw = tf.contrib.rnn.LSTMCell(256) #size is hyperparamter!!!
    fw_state = rnncell_fw.zero_state(batch_size=batchsize, dtype=tf.float32) # batchsize???
    # used variables
    beta = tf.Variable(tf.random_normal([dim_beta])) # size is hyperparamter!!!
    w1 = tf.Variable(tf.random_normal([dim_beta, dim_h])) # dim_beta x dim_h
    w2 = tf.Variable(tf.random_normal([dim_beta, num_features])) # dim_beta x num_features
    wc = tf.Variable(tf.random_normal([dim_o])) # (num_features + dim_h) (x hyperparam) ??? (= dim_o) ???
    wout = tf.Variable(tf.random_normal([num_classes, dim_o])) # num_classes x dim_o
    # initial states, ebenfalls Variablen???
    h0 = tf.zeros([batchsize,dim_h]) # 
    y0 = tf.zeros([batchsize,num_classes]) #
    o0 = tf.zeros([batchsize,dim_o]) #
    l = tf.TensorArray(dtype=tf.float32, size=tf.constant(num_classes))
    params = [tf.constant(0), network, l, h0, y0, o0]
    while_condition = lambda t, network, l, h, y, o: tf.less(t, tf.constant(80)) # token embedding??
    def body(t, network, l, h, y, o):
        e = beta * tanh(w1 * h + w2 * network) # shapes angleichen?? batches??
        alpha = tf.softmax(e)
        c = tf.multiply(alpha,network)
        c = tf.transpose(c, perm=[1,2,0,3]) # put rows and columns in front in order to sum over them
        c = foldl(lambda a, x: a + x, c) # sums over rows
        c = foldl(lambda a, x: a + x, c) # sums over columns
        h = lstm(h, tf.concat([y,o],1)) # was ist mit dem cell state??   # !!!!!      
        o = tanh(wc * tf.concat([h,c],1)) # !!!!!      
        y = softmax(wout * o)
        l = l.write(t, y)
        return [tf.add(t, 1), network, l, h, y, o]
    t, network, l, h, y, o = tf.while_loop(while_condition, body, params)
    return l.stack()

class Model:
    def __init__(self, batchsize):
        self.num_classes = 0
        self.nr_epochs = 1
        self.batchsize = batchsize
        # H,W,batchsize, was bedeutet input_data???
        network = tflearn.layers.core.input_data(shape=[None, None, None, 1])
        self.input_var = network
        # How do I test parts of the network??
        network = createCNNModel(network)
        self.convshape = network
        network, aaa = createEncoderLSTM(network)
        self.encshape = tf.shape(network)
        self.aaa = aaa
        self.aaaNetwork = network

        self.model = tflearn.DNN(network)

    def fit(self, batch):
        self.model.fit(batch['images'], batch['labels'], self.nr_epochs, self.batchsize)



def main(args):
    parameters = process_args(args)
    print("main")
    phase = parameters.phase
    batch_dir = parameters.batch_dir
    assert os.path.exists(batch_dir), batch_dir
    batchfiles = os.listdir(batch_dir)
    batchsize = parameters.batch_size
    model = Model(batchsize)
    sess = tf.Session()
    init_op = tf.global_variables_initializer()
    sess.run(init_op)
    if phase == "training": # epochs!!!
        for i in range(model.nr_epochs):
            for batchfile in batchfiles: # randomise!!!
                print('load ' + batchfile + '!')
                batch = np.load(batch_dir + '/' + batchfile)
                images = batch['images']
                labels = batch['labels']
                model.num_classes = len(labels[0])
                if len(images) != 0:
                    # code.interact(local=locals())
                    # sess.run(model.aaaNetwork, feed_dict={model.input_var:images})
                    print(images.shape)
                    pred = np.array(model.model.predict(images))
                    print(model.convshape.shape)
                    print(pred.shape)
                    # print(model.aaa)
                    #sess.run(model.aaa, feed_dict={model.input_var:images})
                # model.fit(batch) 
    sess.close()           

if __name__ == '__main__':
    main(sys.argv[1:])
    logging.info('Jobs finished')