
'''
CCWP heuristic for arbitrary propagation probabilities.
'''

from __future__ import division
import networkx as nx
from heapq import nlargest
from copy import deepcopy, copy
import os, json, multiprocessing, random
from runIAC import *
from pprint import pprint

def weighted_choice(choices):
    '''
    http://stackoverflow.com/a/3679747/2069858'''
    total = sum(w for c, w in choices)
    r = random.uniform(0, total)
    upto = 0
    for c, w in choices:
        if upto + w > r:
            return c
        upto += w
    assert False, "Shouldn't get here"

def findCC(G, Ep, cascade = "IC"):
    '''
    G is undirected graph
    '''

    # remove blocked edges from graph G
    E = deepcopy(G)
    if cascade == "IC":
        edge_rem = [e for e in E.edges() if random.random() < (1-Ep[e])**(E[e[0]][e[1]]['weight'])]
    elif cascade == "LT":
        for u in G:
            W = [Ep[e] for e in G.edges(u)]
            choices = zip(G.edges(u), W)
            live_edge = weighted_choice(choices)

    E.remove_edges_from(edge_rem)

    # initialize CC
    CC = dict() # each component is reflection of the number of a component to its members
    explored = dict(zip(E.nodes(), [False]*len(E)))
    c = 0
    # perform BFS to discover CC
    for node in E:
        if not explored[node]:
            c += 1
            explored[node] = True
            CC[c] = [node]
            component = E[node].keys()
            for neighbor in component:
                if not explored[neighbor]:
                    explored[neighbor] = True
                    CC[c].append(neighbor)
                    component.extend(E[neighbor].keys())
    return CC

def CCWP((G, k, Ep)):
    '''
     Input:
     G -- undirected graph (nx.Graph)
     k -- number of nodes in seed set (int)
     p -- propagation probability among all edges (int)
     Output:
     scores -- scores of nodes according to some weight function (dict)
    '''
    scores = dict(zip(G.nodes(), [0]*len(G))) # initialize scores

    CC = findCC(G, Ep)

    # find ties for components of rank k and add them all as qualified
    sortedCC = sorted([(len(cc), cc_number) for (cc_number, cc) in CC.iteritems()], reverse=True)
    topCCnumbers = sortedCC[:k] # CCs we assign scores to
    QN = sum([l for (l, _) in topCCnumbers]) # number of qualified nodes

    increment = 0
    try:
        while k+increment < len(sortedCC) and sortedCC[k + increment][0] == sortedCC[k-1][0]:
            topCCnumbers.append(sortedCC[k + increment])
            increment += 1
            QN += sortedCC[k + increment][0]
    except IndexError:
        pass
    # assign scores to nodes in top Connected Components
    prev_length  = topCCnumbers[0][0]
    rank = 1
    QCC = len(topCCnumbers)
    for length, numberCC in topCCnumbers:
        if length != prev_length:
            prev_length = length
            rank += 1
        weighted_score = 1.0/length # updatef = 1
        for node in CC[numberCC]:
            scores[node] += weighted_score
    return scores

def CCWP_directed((G, k, Ep)):
    '''
    Implements Harvester for directed graphs using BFS to explore reach
    Model: IC
    '''

    # add live edges
    if isinstance(G, nx.DiGraph):
        E = nx.DiGraph()
    elif isinstance(G, nx.Graph):
        E = nx.Graph()
    E.add_nodes_from(G.nodes()) # add all nodes in case of isolated components
    live_edges = [edge for edge in G.edges() if random.random() >= (1-Ep[edge])**(G[edge[0]][edge[1]]['weight'])]
    E.add_edges_from(live_edges)
    # E = G

    # Can be optimized using a heap
    # find score for each node
    scores = dict(zip(E.nodes(), [0]*len(E)))
    reachability = dict()
    for node in E:
        reachable_nodes = [node]
        # Do BFS
        out_edges = E.out_edges(node)
        i = 0
        while i < len(out_edges):
            e = out_edges[i]
            if e[1] not in reachable_nodes:
                reachable_nodes.append(e[1])
                out_edges.extend(E.out_edges(e[1]))
            i += 1
        reachability[node] = reachable_nodes
        score = len(reachable_nodes)
        scores[node] = score


    print 'Reachibility', sorted(scores.items(), key=lambda(dk,dv): dv, reverse=True)[:k]
    enhanced_scores = dict()
    sorted_scores = sorted(scores.iteritems(), key = lambda (dk, dv): dv, reverse=True)
    reached_nodes = dict(zip(E.nodes(), [False]*len(E)))

    already_selected = 0
    last_score = 0
    for node, score in sorted_scores:
        if already_selected <= k:
            if not reached_nodes[node]:
                enhanced_scores[node] = score
                reached_nodes.update(dict(zip(reachability[node], [True]*len(reachability[node]))))
                last_score = score
                already_selected += 1
        else:
            if score == last_score:
                if not reached_nodes[node]:
                    enhanced_scores[node] = score
                    reached_nodes.update(dict(zip(reachability[node], [True]*len(reachability[node]))))
            else:
                break
    # print sorted(enhanced_scores.values(), reverse=True)[:k]
    return enhanced_scores

def CCWP_test((G, k, Ep)):
    '''
    Implements Harvester for directed graphs using topological sort
    Model: IC
    '''

    # create live-edge graph
    if isinstance(G, nx.DiGraph):
        E = nx.DiGraph()
    elif isinstance(G, nx.Graph):
        E = nx.Graph()
    E.add_nodes_from(G.nodes()) # add all nodes in case of isolated components
    live_edges = [edge for edge in G.edges() if random.random() >= (1-Ep[edge])**(G[edge[0]][edge[1]]['weight'])]
    E.add_edges_from(live_edges)
    # E = G

    # find CCs and perform topological sort on clusters to find reach
    n2c = dict() # nodes to components
    c2n = dict() # component to nodes
    reachability = dict() # number of nodes can be reached by a node
    # reachability = dict(zip(E.nodes(), [1]*len(E)))


    # find CCs
    scc = nx.strongly_connected_components(E)
    number_scc = -1
    for component in scc:
        number_scc += 1
        c2n[number_scc] = component
        n2c.update(dict(zip(component, [number_scc]*len(component))))

    # create dags with components as nodes
    clusters = nx.DiGraph()
    for node in E:
        # print node, '-->', n2c[node]
        clusters.add_node(n2c[node])
        for out_node in E[node]:
            if n2c[node] != n2c[out_node]:
                clusters.add_edge(n2c[node], n2c[out_node])

    # find reachability performing topological sort
    cluster_reach = dict()
    wccs = nx.weakly_connected_component_subgraphs(clusters)
    i = -1
    for hub in wccs:
        hub_ts = nx.topological_sort(hub, reverse=True)
        for cluster in hub_ts:
            # reach = set()
            reach = []
            for _, out_cluster in clusters.out_edges(cluster):
                reach.extend(cluster_reach[out_cluster])
                # reach.update(cluster_reach[out_cluster])
            # reach.update(c2n[cluster])
            reach.extend(c2n[cluster])
            cluster_reach[cluster] = set(reach)

            reachability.update(dict(zip(c2n[cluster], [len(cluster_reach[cluster])]*len(c2n[cluster]))))
    # print sorted(reachability.items(), key=lambda(dk,dv):dv, reverse=True)
    print 'Reachibility', sorted(reachability.items(), key=lambda(dk,dv):dv, reverse=True)[:k]

    # assign scores to k+ties nodes
    sorted_reach = sorted(reachability.iteritems(), key= lambda (dk,dv): dv, reverse=True)
    min_value = sorted_reach[k-1][1]
    new_idx = k
    new_value = sorted_reach[k][1]
    while new_value == min_value:
        try:
            # scores.update({})
            # scores[sorted_reach[new_idx][0]] = min_value
            new_idx += 1
            new_value = sorted_reach[new_idx][1]
        except IndexError:
            break
    scores = dict(sorted_reach[:new_idx])
    # print sorted(scores.values(), reverse=True)[:k]
    return scores

def frange(begin, end, step):
    x = begin
    y = end
    while x < y:
        yield x
        x += step

def getCoverage((G, S, Ep)):
    return len(runIAC(G, S, Ep))

if __name__ == '__main__':
    import time
    start = time.time()

    dataset = "gnu09"
    model = "Categories"
    print model, dataset

    if model == "MultiValency":
        ep_model = "range1_directed"
    elif model == "Random":
        ep_model = "random1_directed"
    elif model == "Categories":
        ep_model = "degree1_directed"
    elif model == "Weighted":
        ep_model = "weighted1_directed"
    elif model == "Uniform":
        ep_model = "uniform1_directed"

    G = nx.read_gpickle("../../graphs/%s.gpickle" %dataset)
    print 'Read graph G'
    print time.time() - start
    print len(G), len(G.edges())

    Ep = dict()
    with open("Ep/Ep_%s_%s.txt" %(dataset, ep_model)) as f:
        for line in f:
            data = line.split()
            Ep[(int(data[0]), int(data[1]))] = float(data[2])

    #calculate initial set
    R = 1
    I = 500
    ALGO_NAME = "CCWP"
    FOLDER = "Data4InfMax"
    SEEDS_FOLDER = "Seeds"
    TIME_FOLDER = "Time"
    DROPBOX_FOLDER = "/home/sergey/Dropbox/Influence Maximization"
    # seeds_filename = FOLDER + "/" + SEEDS_FOLDER + "/%s_%s_%s_%s.txt" %(SEEDS_FOLDER, ALGO_NAME, dataset, model)
    seeds_filename = FOLDER + "/" + SEEDS_FOLDER + "/%s_%s_%s_%s_directed.txt" %(SEEDS_FOLDER, ALGO_NAME, dataset, model)
    time_filename = FOLDER + "/" + TIME_FOLDER + "/%s_%s_%s_%s.txt" %(TIME_FOLDER, ALGO_NAME, dataset, model)
    logfile = open('log.txt', 'w+')
    # print >>logfile, '--------------------------------'
    # print >>logfile, time.strftime("%c")

    l2c = []
    pool = None
    pool2 = None
    # open file for writing output
    seeds_file = open("%s" %seeds_filename, "a+")
    time_file = open("%s" %time_filename, "a+")
    dbox_seeds_file = open("%s/%s" %(DROPBOX_FOLDER, seeds_filename), "a+")
    dbox_time_file = open("%s/%s" %(DROPBOX_FOLDER, time_filename), "a+")
    for length in range(13, 14, 10):
        time2length = time.time()
        print 'Start finding solution for length = %s' %length
        print >>logfile, 'Start finding solution for length = %s' %length
        time2S = time.time()

        print 'Start mapping...'
        time2map = time.time()
        # define map function
        # def map_CCWP(it):
        #     return CCWP(G, length, Ep)
        if pool == None:
            pool = multiprocessing.Pool(processes=3)
        Scores = pool.map(CCWP_test, ((G, length, Ep) for i in range(R)))
        # print Scores
        print 'Finished mapping in', time.time() - time2map

        # print 'Start mapping...'
        # time2map = time.time()
        # # define map function
        # # def map_CCWP(it):
        # #     return CCWP(G, length, Ep)
        # if pool == None:
        #     pool = multiprocessing.Pool(processes=3)
        # Scores = pool.map(CCWP_directed, ((G, length, Ep) for i in range(R)))
        # # print Scores
        # print 'Finished mapping in', time.time() - time2map

        # print 'Start reducing...'
        # time2reduce = time.time()
        #
        # scores = dict()
        # for Score in Scores:
        #     for node in Score:
        #         try:
        #             scores[node] += Score[node]
        #         except KeyError:
        #             scores[node] = Score[node]
        # scores_copied = deepcopy(scores)
        # S = []
        # # penalization phase
        # for it in range(length):
        #     maxk, maxv = max(scores_copied.iteritems(), key = lambda (dk, dv): dv)
        #     S.append(maxk)
        #     scores_copied.pop(maxk) # remove top element from dict
        #     for v in G[maxk]:
        #         if v not in S and v in scores_copied:
        #             # weight = scores_copied[v]/maxv
        #             # print weight,
        #             penalty = (1-Ep[(maxk, v)])**(G[maxk][v]['weight'])
        #             scores_copied[v] *= penalty
        # print 'Finished reducing in', time.time() - time2reduce
        #
        # print 'Total:', time.time() - start
        #
        # print S
        # print avgIAC(G, S, Ep, 500)
        # # print >>logfile, json.dumps(S)
        # time2complete = time.time() - time2S
        # # with open("%s" %time_filename, "a+") as time_file:
        # #     print >>time_file, (time2complete)
        # # with open("%s/%s" %(DROPBOX_FOLDER, time_filename), "a+") as dbox_time_file:
        # #     print >>dbox_time_file, (time2complete)
        # print 'Finish finding S in %s sec...' %(time2complete)

        # print 'Writing S to files...'
        # with open("%s" %seeds_filename, "a+") as seeds_file:
        #     print >>seeds_file, json.dumps(S)
        # with open("%s/%s" %(DROPBOX_FOLDER, seeds_filename), "a+") as dbox_seeds_file:
        #     print >>dbox_seeds_file, json.dumps(S)

        # print 'Start calculating coverage...'
        # coverage = sum(pool.map(getCoverage, ((G, S, Ep) for _ in range(I))))/I
        # print 'S:', S
        # print 'Coverage', coverage

        # print 'Total time for length = %s: %s sec' %(length, time.time() - time2length)
        # print '----------------------------------------------'

    # seeds_file.close()
    # dbox_seeds_file.close()
    # time_file.close()
    # dbox_time_file.close()
    # logfile.close()

    # Q = nx.DiGraph()
    # Q.add_path([1,2,3,4])
    # Q.add_edge(3,1)
    # Q.add_nodes_from([5,6])
    # Q.add_edge(7,8)
    #
    # start = time.time()
    # reachability_test = CCWP_test((G, 2, Ep))
    # print reachability_test
    # print 'test:', time.time() - start

    # start = time.time()
    # reachability_bench = CCWP_directed((G, 2, Ep))
    # reachability_test = CCWP_test((G, 10, Ep))
    # print reachability_test
    # print 'benchmark:', time.time() - start

    # Q = nx.DiGraph()
    # Q.add_edges_from([(1,2),(2,3),(3,4),(2,5),(5,6), (4,7), (6,7)])
    # Q.add_node(0)
    # print CCWP_test((G,3,Ep))
    # print 'Total time: %s' %(time.time() - start)

    console = []