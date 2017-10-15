import code
import tensorflow as tf
from Decoder import Decoder

class BahdanauDecoder(Decoder):
    def __init__(self, model):
        Decoder.__init__(self, model)

    def createDecoderCell(self):
        rnncell = tf.contrib.rnn.BasicLSTMCell(self.statesize)
        attention = tf.contrib.seq2seq.BahdanauAttention(1024, self.model.features)
        attention_cell = tf.contrib.seq2seq.AttentionWrapper(rnncell, attention)
        return rnncell