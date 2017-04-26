import numpy as np 
from keras.models import Sequential, load_model
from keras.layers.core import Dense, Dropout, Activation, Flatten
from keras.layers.convolutional import Convolution1D
from keras.optimizers import RMSprop, SGD, Adam
from keras.wrappers.scikit_learn import KerasRegressor
import random
import pandas as pd
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn import preprocessing
from sklearn.metrics import make_scorer
import scipy.stats as stats
import logging
import datetime, time

np.random.seed(1337)


#hyperparams include:
#	optimizer ['adam','rms']
#	loss ['mean_squared_error','mean_squared_logarithmic']
#	learning rate [0.001, 0.01, 0.1]
#	hidden layer neurons [(seq_len/8),(seq_len/4),(seq_len/2)]
#	filter batches [20,40,60]
#	filter lengths [(seq_len/50),(seq_len/25),(seq_len/12),(seq_len/6),(seq_len/3)]
#	batch size [32,64,128]
#	epochs [5,10,15]
def create_model(learn_rate=0.001, neurons = 1, seq_len=15):
	########## Build CNN Model #############
	cnn = Sequential()
	cnn.add(Convolution1D(nb_filter=30,filter_length=6,input_dim=4,input_length=seq_len,border_mode="same", activation='relu'))
	cnn.add(Dropout(0.1))
	cnn.add(Convolution1D(nb_filter=40,filter_length=6,input_dim=4,input_length=seq_len,border_mode="same", activation='relu'))

	cnn.add(Flatten())

	#this dense layer should be tuned to various percentages
	#of the first input layer, like [(seq_len*2)/3, seq_len/3]
	cnn.add(Dense(neurons))
	cnn.add(Dropout(0.2))
	cnn.add(Activation('relu'))

	cnn.add(Dense(1))
	cnn.add(Activation('linear'))

	#compile the model
	adam = Adam(lr=learn_rate, beta_1=0.9, beta_2=0.999, epsilon=1e-08)
	#model.compile(loss='mean_squared_error', optimizer=adam)
	rms = RMSprop(lr=learn_rate, rho=0.9, epsilon=1e-08)

	#optimizer, lr, and momeuntum should be tuned
	#need a custom metric (r^2 methinks)
	cnn.compile(loss='mean_squared_error', optimizer=adam)#, metrics=['accuracy'])
	#cnn.compile(loss='mean_squared_logarithmic_error', optimizer=rms)#, metrics=['accuracy'])
	#print 'Model compiled in {0} seconds'.format(time.time() - start_time)
	return cnn

def my_custom_r2_func(ground_truth, predictions):
	#print "Predictions ", predictions.reshape(-1)
	slope, intercept, r_value, p_value, std_err = stats.linregress(ground_truth.reshape(-1),predictions.reshape(-1))
	print "Evaluating a model meow: ", r_value**2
	return r_value**2
	# diff = np.abs(ground_truth - predictions).max()
	# return np.log(1 + diff)



class dnaModel(object):
	""" An optimal CNN model for DNA sequences """

	def __init__(self, input_file):
		"""The input_file should contain only two columns: sequence + expression
		this should create a CNN/model object that is trained and tested optimally (hyperparam opt)"""

		self.filename = ''
		self.model, self.seq_len, self.X_train, self.Y_train, self.X_test, self.Y_test, self.batch, self.epoch = \
				self.__opt_model(input_file)
		

	def __opt_model(self, input_file):
		"""inits/bulids a new model and optimizes hyperparams
		trains/fits and saves best model and params. 
		Currently a simple gridsearch, but should switch to a stochaistic 
		optimization alg with mean performance as the cost fcn """
		
		xtrain, ytrain, xtest, ytest = [], [], [], []

		raw_data = pd.read_excel(input_file, header=0, parse_cols="A,B")
		print raw_data.columns

		######  Cleaning nans out of output column ######
		df = raw_data[np.isfinite(raw_data[u' expression'])]

		############# Format NN inputs #############
		seq_len = len(df['sequence'][0])
		X_data = np.empty([len(df),seq_len,4])
		indx = 0

		Y_data = np.array(df[[u' expression']])

		for seq in df[u'sequence']:
			X_data[indx] = self.__oneHotEncoder(seq)
			indx += 1


		########## RANDOM TEST/TRAIN SPLIT #########
		normed_out = preprocessing.StandardScaler().fit_transform(Y_data)
		xtrain, xtest, ytrain, ytest = train_test_split(X_data, normed_out, test_size=0.15, random_state=42)

		model = KerasRegressor(build_fn=create_model, nb_epoch=6, batch_size=128, verbose=0)

		# define the grid search parameters
		num_bases = [seq_len]
		learn_rate = [0.001]
		neurons = [(seq_len/8),(seq_len/4),(seq_len/2)]
		#momentum = [0.0, 0.2, 0.4, 0.6, 0.8, 0.9]
		param_grid = dict(learn_rate=learn_rate, neurons=neurons, seq_len = num_bases)#, momentum=momentum)

		#specify my own scorer for GridSearchCV that uses r2 instead of the estimator's scorer
		#try RandomizedSearchCV instead of GridSearchCV
		grid = GridSearchCV(estimator=model, param_grid=param_grid, scoring=make_scorer(my_custom_r2_func, greater_is_better=True), n_jobs=1)
		grid_result = grid.fit(xtrain, ytrain)


		# summarize results
		means = grid_result.cv_results_['mean_test_score']
		stds = grid_result.cv_results_['std_test_score']
		params = grid_result.cv_results_['params']
		for mean, stdev, param in zip(means, stds, params):
		    print("%f (%f) with: %r" % (mean, stdev, param))
		print("\n\nBest: %f using %s" % (grid_result.best_score_, grid_result.best_params_))
		print "\nBest Estimator = ", grid_result.best_estimator_

		###################################################################################
		############ Need to extract best params and make a new model with it #############
		###################################################################################
		best_params = grid_result.best_params_
		tuned_model = create_model(best_params['learn_rate'], best_params['neurons'], best_params['seq_len'])
		tuned_model.fit(xtrain, ytrain, batch_size=128, nb_epoch=6, verbose=1)
		predicted = tuned_model.predict(xtest) #.reshape(-1)
		print "NORMED TEST: ", len(ytest)
		print "PREDICTED: ", len(predicted)
		slope, intercept, r_value, p_value, std_err = stats.linregress(ytest.reshape(-1),predicted.reshape(-1))
		print "R2 of tuned_model: ", r_value**2

		return tuned_model, seq_len, xtrain, ytrain, xtest, ytest, 128, 6

	def __oneHotEncoder(self,seq):
		base_dict = {u'A':[1,0,0,0],u'C':[0,1,0,0],u'G':[0,0,1,0],u'T':[0,0,0,1]}
		return np.array([base_dict[x] for x in seq])

	def __oneHotDecoder(self,encseq):
		dec_seq = ""
		for x in encseq:
			if (x == np.array([1,0,0,0])).all():
				dec_seq += u'A'
			elif (x == np.array([0,1,0,0])).all():
				dec_seq += u'C'
			elif (x == np.array([0,0,1,0])).all():
				dec_seq += u'G'
			elif (x == np.array([0,0,0,1])).all():
				dec_seq += u'T'
		return dec_seq

	def __train(self):
		""" loads model that was passed in at the cmdline and trains 
		with input file instead of creating a new model """
		return 0

	def design(self):
		""" outputs best region of dna sequence to mutate to des.txt 
		default resolution is 3 mer, but can be specified as a cmdline param """
		return 0

	def save(self):
		"""creates a HDF5 file of the current model and saves in cur dir"""
		ts = time.time()
		st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
		self.filename = 'dnamodel'+st+'.h5'
		self.model.save(self.filename)  
		return 0

	def test(self):
		"""this will move to test dir but for now just checking that a loaded .h5 file 
		predicts the same thing as the original model predicts (before saving)"""

		test_seqs = [u'A'*self.seq_len, u'C'*self.seq_len, u'G'*self.seq_len, u'T'*self.seq_len]

		print "test sequences = ", test_seqs

		##### format test sequences as CNN input for prediction ####
		Z_test = np.empty([len(test_seqs),self.seq_len,4])
		indx = 0
		for seq in test_seqs:
			Z_test[indx] = self.__oneHotEncoder(seq)
			indx += 1

		print "current model", self.model.predict(Z_test).reshape(-1)
		print "loaded model", load_model(self.filename).predict(Z_test).reshape(-1)
		print self.model.predict(Z_test).reshape(-1)==load_model(self.filename).predict(Z_test).reshape(-1)





