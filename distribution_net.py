import numpy as np
from collections import defaultdict
from scipy import stats
import matplotlib.pyplot as plt

import torch
from scipy.ndimage.filters import gaussian_filter


def kl(p, q):
    p = np.abs(np.asarray(p, dtype=np.float) + 1e-9)
    q = np.abs(np.asarray(q, dtype=np.float) + 1e-9)

    return np.sum(np.where(p != 0, p * np.log(p / q), 0))


def smoothed_hist_kl_distance(a, b, nbins=10, sigma=1):
    ahist, bhist = (np.histogram(a, bins=nbins)[0],
                    np.histogram(b, bins=nbins)[0])
    asmooth, bsmooth = (gaussian_filter(ahist, sigma),
                        gaussian_filter(bhist, sigma))
    return kl(asmooth, bsmooth)


class CustomRequireGrad:

    @staticmethod
    def gram_matrix(layer):
        val = 0
        for ll in layer:
            val += (ll @ ll.T).ravel()
        return val/np.shape(layer)[0]

    @staticmethod
    def _prepare_mean_std_layer(layer):
        normal_dist_pre = np.log(layer)
        vals_pre, axis_val_pre = np.histogram(normal_dist_pre, 100)
        normal_dist_pre[normal_dist_pre < -4] = \
            axis_val_pre[10 + np.argmax(vals_pre[10:])]
        mu = np.mean(normal_dist_pre)
        std = np.std(normal_dist_pre)
        return mu, std

    @staticmethod
    def _concat_func(list_arr):
        init_vec = []
        for vec in list_arr:
            if len(init_vec) == 0:
                init_vec = vec
            else:
                init_vec = np.concatenate([init_vec, vec], axis=1)
        return init_vec

    @staticmethod
    def _plot_distribution(ind_layer, layer_pretrained, layer_test, stats_val):
        num_plots = 9
        # Assuming log normal dist due to relu :
        plt.subplot(np.sqrt(num_plots), np.sqrt(num_plots),
                    ind_layer % num_plots + 1)
        values_pre, axis_val_pre = np.histogram(np.log(layer_pretrained), 100)
        plt.plot(axis_val_pre[10:], values_pre[9:] / np.max(values_pre[10:]),
                 linewidth=4, alpha=0.7, label='D')
        values, axis_val = np.histogram(np.log(layer_test), 100)
        plt.plot(axis_val[10:], values[9:] / np.max(values[10:]), linewidth=4,
                 alpha=0.7, label='D2')
        plt.legend()
        plt.xlim([-5, 3])
        plt.ylim([0, 1 + 0.1])
        plt.title('Layer : ' + str(ind_layer) + 'p: ' + str(np.round(
            stats_val, 2)))

    @ staticmethod
    def plot_activation(layer1, layer2):
        num_kernels = np.shape(layer1)[1]
        num_per_axis = int(np.floor(np.sqrt(num_kernels)))
        for i in range(num_per_axis**2):
            plt.figure(1)
            plt.subplot(num_per_axis, num_per_axis,
                        i + 1)
            plt.imshow(layer1[0][i])
            plt.figure(2)
            plt.subplot(num_per_axis, num_per_axis,
                        i + 1)
            plt.imshow(layer2[0][i])

    def __init__(self, net, pretrained_data_set, input_test):
        self.pretrained_data_set = pretrained_data_set
        self.input_test = input_test
        self.network = net
        self.activation = {}

    def update_grads(self, net, max_layer=8):
        for ind, (name, module) in enumerate(net.named_modules()):
            if ind > max_layer:
                break
            if len(list(module.parameters())) > 0:  # weights
                if len(self.layers_grad_mult[name]) > 0:
                    module.weight.grad *= torch.FloatTensor(
                        self.layers_grad_mult[name]['weights']).cuda()
                    module.bias.grad *= torch.FloatTensor(
                        np.squeeze(self.layers_grad_mult[name]['bias'])).cuda()

    def get_activation(self, name):
        def hook(_, __, output):
            try:
                self.activation[name] = output.detach()
            except:
                self.activation[name] = None

        return hook

    def _prepare_input_tensor(self):
        self.pretrained_iter = map(lambda v: v[0].cuda(),
                                   self.pretrained_data_set)
        self.input_test_iter = map(lambda v: v[0].cuda(), self.input_test)

    def _calc_layers_outputs(self, batches_num=10):
        hooks = {}
        for name, module in self.network.named_modules():
            hooks[name] = module.register_forward_hook(
                self.get_activation(name))
        for ind_batch, (input_model, input_test) \
                in enumerate(zip(self.pretrained_iter,
                                 self.input_test_iter)):
            if ind_batch > batches_num:
                break
            self.activation = {}
            self.network(input_model)
            activations_input = self.activation.copy()
            self.activation = {}
            self.network(input_test)
            activations_input_test = self.activation.copy()
            values_gram_test = 0
            values_gram_pre = 0
            for name, module in self.network.named_modules():
                if activations_input_test[name] is not None:
                    values_test = np.abs(
                        activations_input_test[name].cpu().numpy() + 1e-4)
                    values_pre = np.abs(
                        activations_input[name].cpu().numpy() + 1e-4)

                    values_test2 = None
                    values_pre2 = None
                    if len(np.shape(values_test)) > 2:
                        values_test1 = np.transpose(values_test, [1, 0, 2, 3])
                        values_test2 = np.zeros(((np.shape(values_test1)[0],
                                                  np.prod(np.shape(values_test1)
                                                          [1:]))))
                        values_gram_test = np.zeros((
                            np.shape(values_test1)[0],
                            np.shape(values_test1)[2]**2))
                        values_gram_pre = np.zeros((
                            np.shape(values_test1)[0],
                            np.shape(values_test1)[2]**2))
                        values_pre1 = np.transpose(values_pre, [1, 0, 2, 3])
                        values_pre2 = np.zeros(((np.shape(values_pre1)[0],
                                                 np.prod(np.shape(values_pre1)
                                                         [1:]))))

                        for ll in range(np.shape(values_test1)[0]):
                            values_test2[ll] = np.ravel(values_test1[ll])
                            values_pre2[ll] = np.ravel(values_pre1[ll])
                            values_gram_test[ll] = self.gram_matrix(
                                values_test1[ll])

                            values_gram_pre[ll] = self.gram_matrix(
                                values_pre1[ll])
                        if len(values_pre2[0]) > 20e3:
                            values_test2 = values_test2[:, np.random.randint(
                                0, len(values_pre2[0]), size=4000)]
                            values_pre2 = values_pre2[:, np.random.randint(
                                0, len(values_pre2[0]), size=4000)]

                    self.gram_test[name] += values_gram_test
                    self.gram_pre[name] += values_gram_pre

                    self.statistic_test[name].append(values_test2)
                    self.statistic_pretrained[name].append(values_pre2)

    def _distribution_compare(self, test='kl', plot_dist=False):
        for layer_test, layer_pretrained in (
                zip(self.statistic_test.items(),
                    self.statistic_pretrained.items())):

            stats_value = []
            if not np.sum(layer_pretrained[1][0]) is None:  # has grads layers
                layer_test_concat = self._concat_func(layer_test[1])
                layer_pretrained_concat = self._concat_func(layer_pretrained[1])
                for layer_test_run, layer_pretrained_run in zip(
                        layer_test_concat, layer_pretrained_concat):
                    if test == 't':
                        mu_pre, std_pre = self._prepare_mean_std_layer(
                            layer_pretrained)
                        mu_test, std_test = self._prepare_mean_std_layer(
                            layer_test)
                        test_normal = stats.norm.rvs(
                            loc=mu_test, scale=std_test, size=200)
                        pretrained_normal = stats.norm.rvs(
                            loc=mu_pre, scale=std_pre, size=200)
                        stats_value = stats.ttest_ind(
                            pretrained_normal, test_normal, equal_var=False)[1]
                    if test == 'kl':
                        norm_test = np.log(layer_test_run)
                        norm_pre = np.log(layer_pretrained_run)
                        kl_value = 1 / (1e-9 + smoothed_hist_kl_distance(
                            norm_test, norm_pre, nbins=10, sigma=1))
                        stats_value.append(kl_value)
                self.stats_value_per_layer[layer_test[0]] = stats_value

                if plot_dist:
                    self._plot_distribution(
                        ind_layer=1,
                        layer_pretrained=layer_pretrained[1],
                        layer_test=layer_test[1], stats_val=stats_value[-1])
            else:
                self.stats_value_per_layer[layer_test[0]] = 0

    def _metric_compare(self):
        for ind, (name, module) in enumerate(self.network.named_modules()):
            stats_value = []
            if np.size(self.gram_test[name]) > 1:  # check if has values
                for test, pre in zip(self.gram_test[name],
                                     self.gram_pre[name]):
                    stats_value.append(1/np.mean(np.abs(test - pre)))
            else:
                stats_value = [1e-9]
                self.stats_value_per_layer[name] = stats_value.copy()
            self.stats_value_per_layer[name] = stats_value.copy()

    def _require_grad_search(self):
        th_value = np.median([np.median(val)
                              for key, val in
                              self.stats_value_per_layer.items()])
        th_value = th_value*10
        for ind, (name, module) in enumerate(self.network.named_modules()):
            if (len(list(module.children()))) < 2 and np.size(
                    self.stats_value_per_layer[name]) > 1:
                if ind < len(self.stats_value_per_layer):
                    change_activations = np.ones(np.shape(
                        self.stats_value_per_layer[name]))
                    change_inds = np.where((np.array(self.stats_value_per_layer[
                                                         name]) > th_value) *
                                           (np.array(self.stats_value_per_layer[
                                                         name]) < np.inf))[0]
                    print('layer: ' + name +
                          '  Similar distributions in activation '
                          'num: ' + str(change_inds))
                    change_activations[change_inds] *= 1e-3
                    for weight in module.parameters():
                        new_shape = np.shape(weight)
                        change_activations = np.reshape(
                            change_activations,
                            (len(change_activations), 1, 1, 1))
                        if len(new_shape) > 2:
                            self.layers_grad_mult[name]['weights'] = {}
                            change_activations = np.reshape(
                                change_activations,
                                (len(change_activations), 1, 1, 1))
                            self.layers_grad_mult[name]['weights'] = np.tile(
                                change_activations, (
                                    1, new_shape[1], new_shape[2],
                                    new_shape[3]))
                        else:
                            self.layers_grad_mult[name]['bias'] = {}
                            self.layers_grad_mult[name][
                                'bias'] = change_activations
                else:
                    for _ in module.parameters():
                        self.layers_grad_mult[ind] = None

    def _initialize_parameters(self):
        self.outputs_list = defaultdict(int)
        self.layers_grad_mult = defaultdict(dict)
        self.input_list = defaultdict(int)
        self.stats_value_per_layer = defaultdict(int)
        self.statistic_test = defaultdict(list)
        self.statistic_pretrained = defaultdict(list)
        self.gram_test = defaultdict(int)
        self.gram_pre = defaultdict(int)
        self.list_grads = []
        self.layers_list_to_change = []
        self.layers_list_to_stay = []
        self.mean_var_tested = []
        self.mean_var_pretrained_data = []
        self.stats_value = []

    def run(self, layer_eval_method='gram'):
        self._initialize_parameters()
        self._prepare_input_tensor()
        self._calc_layers_outputs(batches_num=2)
        if layer_eval_method == 'gram':
            self._metric_compare()
        if layer_eval_method == 'distribution':
            self._distribution_compare()
        self._require_grad_search()
