import numpy as np
from scipy.stats import multivariate_normal, entropy
import scipy
from scipy.special import expit
from multiprocessing import Pool
from functools import partial
import matplotlib.pyplot as plt
import torch
from torch.autograd import Variable



### FUNCTION DEFINITIONS ####

# Loss Function
def my_entropy(p_vec, pseudo=0.00000001):
    if np.sum(p_vec) > 0:
        return np.sum([-(p)*np.log((p)) for p in [(x/np.sum(p_vec))+pseudo for x in p_vec]])
    else:
        return 0

def two_class_weighted_entropy(counts, pseudo=.01):
    return (my_entropy([counts[0], counts[1]], pseudo=pseudo)*np.sum(counts[0:2]) + my_entropy([counts[2], counts[3]], pseudo=pseudo)*np.sum(counts[2:4]))/np.sum(counts)

def two_class_weighted_entropy_regularized(counts, weights, regularization=0, pseudo=0.01):
    return (my_entropy([counts[0], counts[1]], pseudo=pseudo)*np.sum(counts[0:2]) + my_entropy([counts[2], counts[3]], pseudo=pseudo)*np.sum(counts[2:4]))/np.sum(counts) + regularization*np.abs(weights).sum()


def modified_entropy(p_vec, pseudo=0.001):
    summed = np.sum(p_vec)
    if summed > 0:
        return entropy(p_vec/summed + pseudo)
    else:
        return 0

def multi_class_weighted_entropy(counts, pseudo=0.001):
    L = int(len(counts)/2)
    first_half = np.array(counts[:L])
    second_half = np.array(counts[L:])

    return (modified_entropy(first_half,pseudo)*first_half.sum()+ modified_entropy(second_half,pseudo)*second_half.sum())/np.sum(counts)

def flip_beta(beta):
    flipped_beta = np.zeros(len(beta))
    for i in range(int(len(beta)/4)):
        flipped_beta[4*i:(4*i+4)] = beta[4*i:(4*i+4)][::-1]                                         
    return flipped_beta

def faster_dot(X_matrices, beta):
    result = np.empty((X_matrices.shape[0],X_matrices.shape[1]))
    for i in range(len(X_matrices)):
        np.dot(X_matrices[i], beta, result[i])
    return result

# CLASSIFY SEQUENCES

def classify_sequences(X_matrices, X_matrices_rc, beta):
    return np.logical_or(np.any(faster_dot(X_matrices, beta) >= 1.0, axis=1), np.any(faster_dot(X_matrices_rc, beta) >= 1.0, axis=1)).astype(int)

def weighted_classify_sequences(X_matrices, X_matrices_rc, beta, weights):
    return np.logical_or(np.any(faster_dot(X_matrices, beta) >= 1.0, axis=1), np.any(faster_dot(X_matrices_rc, beta) >= 1.0, axis=1)).astype(int)
    

def classify_sequence(x, beta, motif_length):
    flipped_beta = beta[::-1]

    scan_length = int((len(x) - len(beta))/4 + 1)
    #print('scan length', scan_length, len(x), len(beta))

    out1 = np.array([np.dot(x[(4*i):(4*i)+len(beta)], beta) for i in range(scan_length)])
    out2 = np.array([np.dot(x[(4*i):(4*i)+len(beta)], flipped_beta) for i in range(scan_length)])

    return int(np.any((out1>1.0) + (out2>1.0)))


def better_return_counts_weighted(labels, classifications, classes, weights):
    output = []
    
    class_indices = []
    for class_value in classes:
        class_indices.append(np.where(labels==class_value)[0])

    #indices_first_class = np.where(labels == classes[0])[0]
    #indices_second_class = np.where(labels == classes[1])[0]
    
    for c in classifications:
        temp = []
        for i in range(2):
            temp.extend([np.sum(weights[np.where(c[indices]==i)[0]]) for indices in class_indices])

        output.append(temp)
        #output.append([np.sum(weights[np.where(c[indices_first_class] == 0)[0]]),
        #              np.sum(weights[np.where(c[indices_second_class] == 0)[0]]),
        #              np.sum(weights[np.where(c[indices_second_class] == 1)[0]]),
        #              np.sum(weights[np.where(c[indices_first_class] == 1)[0]])])
    return np.array(output)

def calculate_prob(N, l, x):
    return 1 - (scipy.special.bdtr(x-1, l, (1/4))**(2*(N-l+1)))

def find_best_div(N, l, proportion):
    best = -1
    closest = 1
    for d in np.arange(1,l+1):
        diff = np.abs((calculate_prob(N, l, d) - proportion))
        if diff < closest:
            closest = diff
            best = d
        else:
            pass
    return best

def x_to_string(x):
    return "".join([str(i) for i in x])

def x_to_matrix(x, motif_length):
    return np.vstack([x[i:i+motif_length*4] for i in range(0,len(x)-(motif_length-1)*4,4)])

def motif_to_beta(motif):
    A = [1.0,0.0,0.0,0.0]
    C = [0.0,1.0,0.0,0.0]
    G = [0.0,0.0,1.0,0.0]
    T = [0.0,0.0,0.0,1.0]
    convertdict = {'A':A, 'C':C, 'G':G, 'T':T}

    return np.array([convertdict[x] for x in motif]).flatten()

## ASSUMES two class ##
def child_variance(y_values, classifications):
    output = []
    classes = np.unique(classifications)
    for i in range(len(classifications)):
        total = 0
        for unique in classes:
            temp_indices = np.where(classifications[i]==unique)[0]
            total += len(temp_indices)*np.var(y_values[temp_indices])
        output.append(total)
    return np.array(output)



#def pytorch_conv(X, X_rc, B, conv, single=False, limit=2000):
#    X_size = X.size(0)
#    result = np.empty((0,X_size), dtype=np.float64)
#    for i in range(int(len(B)/limit)):
#        conv.weight.data = torch.from_numpy(B[i*limit:(i+1)*limit].reshape(limit,1,len(B[0]))).float()
#        if torch.cuda.is_available():
#            conv.cuda()
#            
#        output = conv(X)
#        max_output = np.swapaxes((torch.max(dim=2)[0] > 1.0).cpu().data.numpy(),0,1)
#        result = np.append(result, max_output, axis=0)
#
#    return result


def pytorch_convDNA(X, X_rc, B, conv, single=False, limit=2000):
    X_size = X.size(0)
    result = np.empty((0,X_size), dtype=np.float64)
    for i in range(int(len(B)/limit)):
        conv.weight.data = torch.from_numpy(B[i*limit:(i+1)*limit].reshape(limit,1,len(B[0]))).float()
        if torch.cuda.is_available():
            conv.cuda()
            
        output1 = conv(X)
        output2 = conv(X_rc)
        max_output = np.swapaxes((torch.max(output1, output2).max(dim=2)[0] > 1.0).cpu().data.numpy(),0,1)
        result = np.append(result, max_output, axis=0)

    return result

def pytorch_conv2d(X, B, conv, threshold=3000, limit=100):
    X_size = X.size(0)
    result = np.empty((0,X_size), dtype=np.float64)
    for i in range(int(len(B)/limit)):
        conv.weight.data = torch.from_numpy(B[i*limit:(i+1)*limit].reshape(limit,1,B.shape[1],B.shape[2])).float()
        conv = conv.cuda()
        output = np.swapaxes((conv(X).max(dim=2)[0].max(dim=2)[0] > threshold).cpu().data.numpy(),0,1)
        result = np.append(result, output, axis=0)
    return result

def pytorch_conv_exact2d(X, B, conv, threshold=500, limit=50):
    X_size = X.size(0)
    X=X.cuda()
    result = np.empty((0,X_size), dtype=np.float64)
    conv.out_channels = limit
    for i in range(int(len(B)/limit)):
        conv.weight.data = torch.from_numpy(B[i*limit:(i+1)*limit].reshape(limit,1,B.shape[1],B.shape[2])).float()
        conv = conv.cuda()
        output = np.swapaxes((conv(X).max(dim=2)[0].max(dim=2)[0] > threshold).cpu().data.numpy(),0,1)
        result = np.append(result, output, axis=0)

    leftover = len(B) % limit
    conv.out_channels = leftover
    conv.weight.data = torch.from_numpy(B[(-1)*leftover:].reshape(leftover,1,B.shape[1],B.shape[2])).float()
    conv = conv.cuda()
    output = np.swapaxes((conv(X).max(dim=2)[0].max(dim=2)[0] > threshold).cpu().data.numpy(),0,1)
    result = np.append(result, output, axis=0)

    return result
