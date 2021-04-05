import torch.nn as nn
import numpy as np
from torchvision import transforms, datasets
import torch.optim as optim
import torch.nn.functional as F
from torch.nn import Module
import math
import torch
from torch import Tensor
from torch.nn.parameter import Parameter, UninitializedParameter
from torch.nn import init
transform = transforms.Compose([transforms.Resize((64, 64)),
                                transforms.ToTensor(), transforms.Normalize((0.5, 0.5, 0.5),
                                                                            (0.5, 0.5, 0.5))])
transform = transforms.Compose([transforms.ToTensor(),transforms.Resize((64, 64)),
                                transforms.Normalize((0.1307,), (0.3081,))])

class KernelLinear(Module):

    def __init__(self, in_features: int, out_features: int, bias: bool = True) -> None:
        super(KernelLinear, self).__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.weight = Parameter(torch.Tensor(out_features, in_features))
        self.register_parameter('bias', None)
        self.reset_parameters()
        self.output = torch.ones((20,10))


    def reset_parameters(self) -> None:
        init.kaiming_uniform_(self.weight, a=np.sqrt(5))
        if self.bias is not None:
            fan_in, _ = init._calculate_fan_in_and_fan_out(self.weight)
            bound = 1 / math.sqrt(fan_in)
            init.uniform_(self.bias, -bound, bound)

    def forward(self, input: Tensor) -> Tensor:
        sigma = 1
        for i, w in enumerate(self.weight):
            self.output[:,i] = torch.log(torch.exp( -1*torch.sqrt(torch.sum((w - input )**2,axis=1)) /(2*sigma)))
        return self.output

    def extra_repr(self) -> str:
        return 'in_features={}, out_features={}, bias={}'.format(
            self.in_features, self.out_features, self.bias is not None
        )

class Simple_Net(nn.Module):
    def __init__(self):
        super(Simple_Net, self).__init__()
        self.conv1 = nn.Conv2d(1, 500, 7)
        self.batch_norm1 = nn.BatchNorm2d(500)
        self.pool = nn.MaxPool2d(2, 2)
        self.batch_norm2 = nn.BatchNorm2d(100)
        self.conv2 = nn.Conv2d(500, 100, 3)
        self.conv3 = nn.Conv2d(100, 10, 3)
        self.fc1 = nn.Linear(10 * 5 * 5, 10)

    def forward(self, x):
        x = self.pool(self.batch_norm1(F.relu(self.conv1(x))))
        x = self.pool(self.batch_norm2(F.relu(self.conv2(x))))
        x = self.pool(F.relu(self.conv3(x)))
        x = x.view(-1, 10 * 5 * 5)
        x = F.sigmoid(self.fc1(x))
        return x

class Simple_Net(nn.Module):
    def __init__(self):
        super(Simple_Net, self).__init__()
        self.conv1 = nn.Conv2d(1, 20, 7)
        self.batch_norm1 = nn.BatchNorm2d(20)
        self.pool = nn.MaxPool2d(2, 2)
        self.batch_norm2 = nn.BatchNorm2d(20)
        self.conv2 = nn.Conv2d(20, 20, 3)
        self.conv3 = nn.Conv2d(20, 20, 3)
        self.fc1 = KernelLinear(20 * 5 * 5, 10)
        #self.fc1 = nn.Linear(20 * 5 * 5, 10)
        self.weight = Parameter(torch.Tensor(10, 500))

    def forward(self, x):
        x = self.pool(self.batch_norm1(F.relu(self.conv1(x))))
        x = self.pool(self.batch_norm2(F.relu(self.conv2(x))))
        x = self.pool(F.relu(self.conv3(x)))
        x = x.view(-1, 20 * 5 * 5)
        sigma = 1
        self.output = torch.zeros((1,10)).cuda()
        for i, X in enumerate(x):
            self.output+= torch.log(torch.exp( -1*torch.sqrt(torch.sum((self.weight - X )**2,axis=1)) /(2*sigma)))
        x = F.softmax(self.output)
        return x

class diff_net(Simple_Net):
    def __init__(self):
        super(diff_net, self).__init__()
        self.group_n_0 = torch.nn.GroupNorm(1, 1, eps=1e-05, affine=True)
        self.group_n_1 = torch.nn.GroupNorm(4, 100, eps=1e-05, affine=True)
        self.group_n_1 = torch.nn.GroupNorm(4, 100, eps=1e-05, affine=True)
        self.group_n_2 = torch.nn.GroupNorm(4, 100, eps=1e-05, affine=True)

    def forward(self, x):

        x = self.pool(self.batch_norm1(F.relu(self.conv1(self.group_n_0(x)))))
        x = self.pool(self.batch_norm2(F.relu(self.conv2(self.group_n_1(x)))))
        x = F.relu(self.conv3(self.group_n_2(x)))
        x = x.view(-1, 100 * 11 * 11)
        x = F.sigmoid(self.fc1(x))
        return x


if __name__ == '__main__':
    batch_size  = 20
    dataset_first = datasets.CIFAR10(root='.', train=True, download=True,
                                     transform=transform)
    trainloader = torch.utils.data.DataLoader(dataset_first, batch_size=batch_size,
                                              shuffle=True)
    dataset_test = datasets.CIFAR10(root='.', train=False, download=True,
                                     transform=transform)
    testloader = torch.utils.data.DataLoader(dataset_test, batch_size=batch_size,
                                              shuffle=False)

    dataset_first = datasets.KMNIST(root='.', train=True, download=True,transform=transform)
    trainloader = torch.utils.data.DataLoader(dataset_first, batch_size=batch_size,
                                              shuffle=True)

    dataset_test = datasets.KMNIST(root='.', train=False, download=True,transform=transform)
    testloader = torch.utils.data.DataLoader(dataset_test, batch_size=batch_size,
                                              shuffle=False)


    net = Simple_Net().cuda()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(net.parameters(), lr=1e-3, momentum=0.9)
    cycle_opt = torch.optim.lr_scheduler.CyclicLR(optimizer, 1e-3, 5e-3,
                                      step_size_up=100)

    accuracy = []
    loss = []
    for epoch in range(40):  # loop over the dataset multiple times
        running_loss = 0.0
        for i, data in enumerate(trainloader, 0):
            # get the inputs; data is a list of [inputs, labels]
            inputs, labels = data
            #plt.imshow(inputs.detach().cpu().numpy()[0].transpose())
            optimizer.zero_grad()
            outputs = net(inputs.cuda())
            loss = criterion(outputs.cuda(), labels.cuda())
            loss.backward(retain_graph=True)
                #if epoch > 25:
                  #  optimizer.param_groups[0]['lr'] = 1e-5
            optimizer.step()
            cycle_opt.step()
            running_loss += loss.item()
        print('[%d, %5d] loss: %.3f' %
              (epoch + 1, i + 1, running_loss / i))
        correct = 0
        total = 0
        count = 0
        with torch.no_grad():
            for data in testloader:
                count += 1
                images, labels = data
                outputs = net(images.cuda())
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += np.array((predicted.detach().cpu() == labels)).sum()
                if count > 250:
                    break
        torch.save(net.state_dict(),r'C:\Users\yuval\PycharmProjects\smart_pretrained\Statistics-pretrained\saved_models\model'+str(epoch))

        print(
            'Accuracy of the network on the 10000 test images: %d %%' % (
                    100 * correct / total))
        #writer.add_scalar('Test - Accuracy',
        #                  (100 * correct / total),
        #                   epoch)
        #writer.add_scalar('Train - Loss',
        #                  (running_loss / i),
        #                   epoch)
        #writer.add_scalar('LR',
        #                  (optimizer.param_groups[0]['lr']),
        #                   epoch)
#
        accuracy.append((epoch,100 * correct / total ))
        running_loss = 0.0