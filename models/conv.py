import torch
from torch_geometric.nn import MessagePassing
import torch.nn.functional as F
from torch_geometric.nn import global_mean_pool, global_add_pool
from torch_geometric.utils import degree, is_undirected, to_undirected
from ogb.graphproppred.mol_encoder import AtomEncoder, BondEncoder

"""
Modified from OGB PyG implementation
"""

### GIN convolution along the graph structure
class GINConv(MessagePassing):

    def __init__(self, emb_dim, edge_dim=3, mitigation_backbone=None):
        '''
            emb_dim (int): node embedding dimensionality
        '''

        super(GINConv, self).__init__(aggr="add")

        self.mlp = torch.nn.Sequential(torch.nn.Linear(emb_dim, 2 * emb_dim), torch.nn.BatchNorm1d(2 * emb_dim),
                                       torch.nn.ReLU(), torch.nn.Linear(2 * emb_dim, emb_dim))
        self.eps = torch.nn.Parameter(torch.Tensor([0]))

        if edge_dim == 1:
            self.edge_encoder = BondEncoder(emb_dim=emb_dim)
        elif edge_dim > 0:
            self.edge_encoder = torch.nn.Linear(edge_dim, emb_dim)
        self.edge_dim = edge_dim

        self.mitigation_backbone = mitigation_backbone
        if mitigation_backbone:
            self.attn = []
            self.mitigation_attn = torch.nn.Sequential(
                torch.nn.Linear(2 * emb_dim, 1),
                # torch.nn.BatchNorm1d(4 * emb_dim),
                # torch.nn.ReLU(),
                # torch.nn.Linear(2 * emb_dim, 1)
            )

    def forward(self, x, edge_index, edge_attr, return_attn_distrib=False):
        # print()
        # print("Undirected: ", is_undirected(edge_index))
        # edge_index = to_undirected(edge_index)
        # for i in range(x.shape[0]):
        #     x[i] = torch.tensor([i]*x.shape[1], dtype=float)
        # print(x.shape, edge_index.shape, edge_index[:,0])
        # print(x[edge_index[:,0],:10])
        # print(degree(edge_index[0,:]))
        if self.edge_dim == -1:
            edge_embedding = edge_attr
        else:
            if self.edge_dim == 1:
                edge_attr = edge_attr.long()
            edge_embedding = self.edge_encoder(edge_attr)
        out = self.mlp((1 + self.eps) * x + self.propagate(edge_index, x=x, edge_attr=edge_embedding, return_attn_distrib=return_attn_distrib))

        return out

    def message(self, x_i, x_j, edge_attr, index, return_attn_distrib):
        # print("-"*100)
        # print(x_i.shape, x_j.shape, index.shape)
        # print(x_i[:,:10])
        # print()
        # print(x_j[:,:10])
        # print(index)
        # print(torch.unique(index, return_counts=True))
        # exit()

        if self.mitigation_backbone:
            attn = self.mitigation_attn(torch.cat([x_i, x_j], dim=-1))
            attn = torch.sigmoid(attn)
            
            if return_attn_distrib:
                self.attn.extend(attn.detach().cpu().squeeze().numpy().tolist())
            
            # attn_hard = (attn > 0.5).float()
            # attn = attn_hard - attn.detach() + attn

            x_j = x_j * attn

        if self.edge_dim < 0:
            return F.relu(x_j)
        return F.relu(x_j + edge_attr)

    def update(self, aggr_out):
        return aggr_out


### GCN convolution along the graph structure
class GCNConv(MessagePassing):

    def __init__(self, emb_dim, edge_dim=-1, mitigation_backbone=None):
        super(GCNConv, self).__init__(aggr='add')

        self.linear = torch.nn.Linear(emb_dim, emb_dim)
        self.root_emb = torch.nn.Embedding(1, emb_dim)
        if edge_dim == 1:
            self.edge_encoder = BondEncoder(emb_dim=emb_dim)
        elif edge_dim > 0:
            self.edge_encoder = torch.nn.Linear(edge_dim, emb_dim)
        self.edge_dim = edge_dim

        self.mitigation_backbone = mitigation_backbone
        if mitigation_backbone:
            self.attn = []
            self.mitigation_attn = torch.nn.Sequential(
                torch.nn.Linear(2 * emb_dim, 1),
                # torch.nn.BatchNorm1d(4 * emb_dim),
                # torch.nn.ReLU(),
                # torch.nn.Linear(2 * emb_dim, 1)
            )

    def forward(self, x, edge_index, edge_attr, return_attn_distrib=False):
        x = self.linear(x)
        if self.edge_dim == -1:
            edge_embedding = edge_attr
        else:
            if self.edge_dim == 1:
                edge_attr = edge_attr.long()
            edge_embedding = self.edge_encoder(edge_attr)

        row, col = edge_index

        deg = degree(row, x.size(0), dtype=x.dtype) + 1
        deg_inv_sqrt = deg.pow(-0.5)
        deg_inv_sqrt[deg_inv_sqrt == float('inf')] = 0

        norm = deg_inv_sqrt[row] * deg_inv_sqrt[col]

        return self.propagate(edge_index,
                    x=x,
                    edge_attr=edge_embedding,
                    norm=norm,
                    return_attn_distrib=return_attn_distrib
                ) + F.relu(x + self.root_emb.weight) * 1. / deg.view(-1, 1)

    def message(self, x_i, x_j, edge_attr, norm, return_attn_distrib):
        if self.mitigation_backbone:
            attn = self.mitigation_attn(torch.cat([x_i, x_j], dim=-1))
            attn = torch.sigmoid(attn)
            
            if return_attn_distrib:
                self.attn.extend(attn.detach().cpu().squeeze().numpy().tolist())
            
            # attn_hard = (attn > 0.5).float()
            # attn = attn_hard - attn.detach() + attn

            x_j = x_j * attn

        if self.edge_dim < 0:
            return norm.view(-1, 1) * F.relu(x_j)
        return norm.view(-1, 1) * F.relu(x_j + edge_attr)

    def update(self, aggr_out):
        return aggr_out


### GNN to generate node embedding
class GNN_node(torch.nn.Module):
    """
    Output:
        node representations
    """

    def __init__(self,
                 num_layer,
                 emb_dim,
                 input_dim=1,
                 drop_ratio=0.5,
                 JK="last",
                 residual=False,
                 gnn_type='gin',
                 edge_dim=-1,
                 mitigation_backbone=None):
        '''
            emb_dim (int): node embedding dimensionality
            num_layer (int): number of GNN message passing layers

        '''

        super(GNN_node, self).__init__()
        self.num_layer = num_layer
        self.drop_ratio = drop_ratio
        self.JK = JK
        ### add residual connection or not
        self.residual = residual

        # if self.num_layer < 2:
        #     raise ValueError("Number of GNN layers must be greater than 1.")

        if input_dim == 1:
            self.node_encoder = AtomEncoder(emb_dim)  # uniform input node embedding
            self.edge_dim = 1
        elif input_dim == -1:
            # ogbg-ppa
            self.node_encoder = torch.nn.Embedding(1, emb_dim)  # uniform input node embedding
            self.edge_dim = 7
        elif edge_dim != -1:
            # drugood
            self.node_encoder = torch.nn.Linear(input_dim, emb_dim)  # uniform input node embedding
            self.edge_dim = edge_dim
        else:
            # only for spmotif dataset
            self.node_encoder = torch.nn.Linear(input_dim, emb_dim)
            self.edge_dim = -1
        ###List of GNNs
        self.convs = torch.nn.ModuleList()
        self.batch_norms = torch.nn.ModuleList()

        for layer in range(num_layer):
            if gnn_type == 'gin':
                self.convs.append(GINConv(emb_dim, edge_dim=self.edge_dim, mitigation_backbone=mitigation_backbone))
            elif gnn_type == 'gcn':
                self.convs.append(GCNConv(emb_dim, edge_dim=self.edge_dim, mitigation_backbone=mitigation_backbone))
            else:
                ValueError('Undefined GNN type called {}'.format(gnn_type))

            self.batch_norms.append(torch.nn.BatchNorm1d(emb_dim))

    def forward(self, batched_data, return_attn_distrib=False):
        x, edge_index, edge_attr, batch = batched_data.x, batched_data.edge_index, batched_data.edge_attr, batched_data.batch
        ### computing input node embedding
        h_list = [self.node_encoder(x)]
        for layer in range(self.num_layer):
            h = self.convs[layer](h_list[layer], edge_index, edge_attr, return_attn_distrib)
            h = self.batch_norms[layer](h)

            if layer == self.num_layer - 1:
                #remove relu for the last layer
                h = F.dropout(h, self.drop_ratio, training=self.training)
            else:
                h = F.dropout(F.relu(h), self.drop_ratio, training=self.training)

            if self.residual:
                h += h_list[layer]

            h_list.append(h)

        ### Different implementations of Jk-concat
        if self.JK == "last":
            node_representation = h_list[-1]
        elif self.JK == "sum":
            node_representation = 0
            for layer in range(self.num_layer):
                node_representation += h_list[layer]

        return node_representation


### Virtual GNN to generate node embedding
class GNN_node_Virtualnode(torch.nn.Module):
    """
    Output:
        node representations
    """

    def __init__(self,
                 num_layer,
                 emb_dim,
                 input_dim=1,
                 drop_ratio=0.5,
                 JK="last",
                 residual=False,
                 gnn_type='gin',
                 edge_dim=-1):
        '''
            emb_dim (int): node embedding dimensionality
        '''

        super(GNN_node_Virtualnode, self).__init__()
        self.num_layer = num_layer
        self.drop_ratio = drop_ratio
        self.JK = JK
        ### add residual connection or not
        self.residual = residual

        if self.num_layer < 2:
            raise ValueError("Number of GNN layers must be greater than 1.")

        if input_dim == 1:
            self.node_encoder = AtomEncoder(emb_dim)  # uniform input node embedding
            self.edge_dim = 1
        elif input_dim == -1:
            # ogbg-ppa
            self.node_encoder = torch.nn.Embedding(1, emb_dim)  # uniform input node embedding
            self.edge_dim = 7
        elif edge_dim != -1:
            # drugood
            self.node_encoder = torch.nn.Linear(input_dim, emb_dim)  # uniform input node embedding
            self.edge_dim = edge_dim
        else:
            # only for spmotif dataset
            self.node_encoder = torch.nn.Linear(input_dim, emb_dim)
            self.edge_dim = -1
        ### set the initial virtual node embedding to 0.
        self.virtualnode_embedding = torch.nn.Embedding(1, emb_dim)
        torch.nn.init.constant_(self.virtualnode_embedding.weight.data, 0)

        ### List of GNNs
        self.convs = torch.nn.ModuleList()
        ### batch norms applied to node embeddings
        self.batch_norms = torch.nn.ModuleList()

        ### List of MLPs to transform virtual node at every layer
        self.mlp_virtualnode_list = torch.nn.ModuleList()

        for layer in range(num_layer):
            if gnn_type == 'gin':
                self.convs.append(GINConv(emb_dim, edge_dim=self.edge_dim))
            elif gnn_type == 'gcn':
                self.convs.append(GCNConv(emb_dim, edge_dim=self.edge_dim))
            else:
                ValueError('Undefined GNN type called {}'.format(gnn_type))

            self.batch_norms.append(torch.nn.BatchNorm1d(emb_dim))

        for layer in range(num_layer - 1):
            # https://discuss.pytorch.org/t/batchnorm1d-cuda-error-an-illegal-memory-access-was-encountered/127641/5
            self.mlp_virtualnode_list.append(torch.nn.Sequential(torch.nn.Linear(emb_dim, 2*emb_dim), torch.nn.BatchNorm1d(2*emb_dim), torch.nn.ReLU(), \
                                                    torch.nn.Linear(2*emb_dim, emb_dim), torch.nn.BatchNorm1d(emb_dim), torch.nn.ReLU()))

    def forward(self, batched_data):

        x, edge_index, edge_attr, batch = batched_data.x, batched_data.edge_index, batched_data.edge_attr, batched_data.batch

        ### virtual node embeddings for graphs
        virtualnode_embedding = self.virtualnode_embedding(
            torch.zeros(batch[-1].item() + 1).to(edge_index.dtype).to(edge_index.device))
        h_list = [self.node_encoder(x)]
        for layer in range(self.num_layer):
            ### add message from virtual nodes to graph nodes
            h_list[layer] = h_list[layer] + virtualnode_embedding[batch]

            ### Message passing among graph nodes
            h = self.convs[layer](h_list[layer], edge_index, edge_attr)

            h = self.batch_norms[layer](h)
            if layer == self.num_layer - 1:
                #remove relu for the last layer
                h = F.dropout(h, self.drop_ratio, training=self.training)
            else:
                h = F.dropout(F.relu(h), self.drop_ratio, training=self.training)

            if self.residual:
                h = h + h_list[layer]

            h_list.append(h)

            ### update the virtual nodes
            if layer < self.num_layer - 1:
                ### add message from graph nodes to virtual nodes
                virtualnode_embedding_temp = global_add_pool(h_list[layer], batch) + virtualnode_embedding
                ### transform virtual nodes using MLP

                if self.residual:
                    virtualnode_embedding = virtualnode_embedding + F.dropout(
                        self.mlp_virtualnode_list[layer](virtualnode_embedding_temp),
                        self.drop_ratio,
                        training=self.training)
                else:
                    virtualnode_embedding = F.dropout(self.mlp_virtualnode_list[layer](virtualnode_embedding_temp),
                                                      self.drop_ratio,
                                                      training=self.training)

        ### Different implementations of Jk-concat
        if self.JK == "last":
            node_representation = h_list[-1]
        elif self.JK == "sum":
            node_representation = 0
            for layer in range(self.num_layer):
                node_representation += h_list[layer]

        return node_representation


if __name__ == "__main__":
    pass
