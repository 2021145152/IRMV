// Get complete information about object(s)
// Parameters: object_ids (list of IDs)

MATCH (obj:Individual)
WHERE obj.id IN $object_ids
OPTIONAL MATCH (obj)-[r]->(target)
WHERE type(r) <> 'INSTANCE_OF'

WITH obj, collect(DISTINCT {type: type(r), target: target.id}) AS relationships

RETURN
    obj.id AS id,
    properties(obj) AS properties,
    relationships
ORDER BY obj.id
