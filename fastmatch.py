"""
Fast matching algorithm for image matching

Jonas Toft Arnfred, 2013-05-05
"""

####################################
#                                  #
#            Imports               #
#                                  #
####################################

from matchutil import get_features
import cv2
from imaging import get_thumbnail, get_size
import numpy
import itertools


####################################
#                                  #
#           Functions              #
#                                  #
####################################

def match_thumbs(path, cache, thumb_size = (200, 200)) :
    # Load target and find descriptors and size
    target = get_thumbnail(path, thumb_size)
    t_orig_size = get_size(path)
    get_features(target)
    t_keypoints, t_descriptors = get_features(target)

    # Similar for query
    q_descriptors = cache.thumb["descriptors"]
    q_distances = cache.thumb["distances"]
    q_pos = cache.thumb["positions"]
    # match thumbnails and find ratio
    matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)
    matches = [m for m in matcher.knnMatch(q_descriptors, t_descriptors, k=1) if len(m) > 0]
    ratios = numpy.array([m[0].distance / q_distances[m[0].queryIdx] for m in matches])

    # Get positions of points and their scaling factor
    t_pos = [t_keypoints[m[0].trainIdx].pt for m in matches]
    t_ratio_x = t_orig_size[0]/float(target.shape[1])
    t_ratio_y = t_orig_size[1]/float(target.shape[0])
    t_ratio = numpy.array([t_ratio_x, t_ratio_y])

    q_pos = numpy.array([cache.thumb["positions"][m[0].queryIdx] for m in matches])
    q_ratio_x = cache.original["size"][0]/float(cache.thumb["size"][0])
    q_ratio_y = cache.original["size"][1]/float(cache.thumb["size"][1])
    q_ratio = numpy.array([q_ratio_x, q_ratio_y])

    # Sort ratios and scale positions
    indices = numpy.argsort(ratios)
    pos_scaled = numpy.array([(q_p * q_ratio, t_p * t_ratio) for q_p, t_p in zip(q_pos, t_pos)])
    return pos_scaled[indices], ratios[indices]


# Match point strategy #1:
def match_position(pos, cache, target) :
    # Find positions
    pos_cache = pos[0]
    pos_target = pos[1]

    # Find radius (average of height and width of target grid cell)
    r = int(numpy.mean(target.cell_size))

    # Find descriptors inside circle with radius r = square_size
    # This gives a bigger circle than rectangle, but there is no harm done
    cache_ds, cache_pos, cache_dis = cache.get(pos_cache, r)

    target_kp, target_ds = target.get(pos_target)
    if target_ds == None :
        return numpy.array([]), numpy.array([])
    offset_x, offset_y = target.offset(pos_target)
    target_pos = [numpy.array([k.pt[0]+offset_x, k.pt[1]+offset_y]) for k in target_kp]

    # Match descriptors using bf
    matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=True)
    matches = [m for m in matcher.knnMatch(cache_ds, target_ds, k=1) if len(m) > 0]

    # Distances to nearest neighbor and positions
    ratios = numpy.array([m[0].distance / cache_dis[m[0].queryIdx] for m in matches])
    positions = numpy.array([(cache_pos[m[0].queryIdx], target_pos[m[0].trainIdx]) for m in matches])
    ratio_indices = numpy.argsort(ratios)

    return positions[ratio_indices], ratios[ratio_indices]


def log_iter(query_pos, target_pos, result_pos, target_grid, ratios, tau) :
    return {
        "query_pos" : query_pos,
        "target_pos" : target_pos,
        "target_grid" : target_grid.last,
        "matches" : result_pos[ratios<tau],
        "radius" : numpy.mean(target_grid.cell_size),
        "ratios" : ratios[ratios<tau],
        "margin" : target_grid.margin }

def do_iter(positions, cache, target_grid, tau = 0.85, log = None) :
    while True :
        query_pos, target_pos = positions.next()
        if not target_grid.is_cached(target_pos) :
            result_pos, ratios = match_position((query_pos, target_pos), cache, target_grid)
            # For each match we don't discard, we might want to examine the neighbor field
            get_neighbor = lambda point : target_grid.get_neighbor(target_grid.block(target_pos), point)
            neighbor_pos = [(p[0], get_neighbor(p[1])) for p in result_pos[ratios<tau]]
            neighbor_pos_filtered = numpy.array([p for p in neighbor_pos if p[1] != None])
            # Add new neighbor positions to positions
            if len(neighbor_pos_filtered) > 0 :
                positions = itertools.chain(neighbor_pos_filtered, positions)
            # Log if we have to
            if log != None :
                log.append(log_iter(query_pos, target_pos, result_pos, target_grid, ratios, tau))
            # Yield result
            for match in zip(result_pos[ratios<tau], ratios[ratios<tau]) :
                yield match

def match(positions, cache, target_grid, tau = 0.85, log = None) :
    positions_iter = itertools.chain(positions)
    return zip(*do_iter(positions_iter, cache, target_grid, tau = tau, log = log))
