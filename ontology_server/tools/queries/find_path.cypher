// Find shortest path between two locations using GDS Dijkstra
// Handles both object IDs and space IDs
// Parameters: from_id, to_id

// Resolve source and target locations (if object, get its space; if space, use directly)
MATCH (source_input:Individual {id: $from_id})
MATCH (target_input:Individual {id: $to_id})
OPTIONAL MATCH (source_input)-[:isInSpace]->(source_space:Space)
OPTIONAL MATCH (target_input)-[:isInSpace]->(target_space:Space)

WITH
    CASE
        WHEN source_space IS NOT NULL THEN source_space
        WHEN source_input:Space THEN source_input
    END AS source,
    CASE
        WHEN target_space IS NOT NULL THEN target_space
        WHEN target_input:Space THEN target_input
    END AS target

// Run Dijkstra shortest path
CALL gds.shortestPath.dijkstra.stream('spatialGraph', {
    sourceNode: source,
    targetNode: target,
    relationshipWeightProperty: 'weight'
})
YIELD totalCost, nodeIds

// Convert node IDs to node info
UNWIND range(0, size(nodeIds)-1) AS idx
WITH totalCost, nodeIds, idx, gds.util.asNode(nodeIds[idx]) AS node

RETURN
    collect({index: idx, id: node.id}) AS path,
    totalCost AS cost,
    size(nodeIds) AS num_nodes
