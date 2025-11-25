// Filter objects by various criteria (template - will be dynamically built)
// Parameters: class_type, affordance, in_space, in_storey, has_relationship

// Base query
MATCH (obj:Individual)

// Filter by class type (if provided)
// WHERE 'ClassName' IN labels(obj)

// Filter by affordance (if provided)
// MATCH (obj)-[:affords]->(aff:Affordance {id: $affordance})

// Filter by space (if provided)
// MATCH (obj)-[:objectIsInSpace]->(space:Space {id: $in_space})

// Filter by storey (if provided)
// MATCH (obj)-[:objectIsInSpace]->(space:Space)-[:roomIsInStorey|corridorIsInStorey]->(storey:Storey {id: $in_storey})

// Filter by relationship (if provided)
// MATCH (obj)-[:relationshipType]->(target:Individual {id: $target_id})

// Get additional information
OPTIONAL MATCH (obj)-[:objectIsInSpace|robotIsInSpace]->(space:Space)
OPTIONAL MATCH (space)-[:roomIsInStorey|corridorIsInStorey]->(storey:Storey)
OPTIONAL MATCH (obj)-[:affords]->(aff:Affordance)

RETURN
    obj.id AS id,
    labels(obj) AS types,
    obj.comment AS comment,
    space.id AS space_id,
    storey.id AS storey_id,
    obj.x AS x,
    obj.y AS y,
    obj.isOpen AS is_open,
    collect(DISTINCT aff.id) AS affordances
ORDER BY obj.id
