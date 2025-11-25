;; ====================================================================
;; Robot Manipulation Domain
;; - Affordance-based design
;; - Derived predicates for state computation
;; - Action costs for optimal planning
;; ====================================================================

(define (domain robot)
  (:requirements
    :strips :typing :negative-preconditions :existential-preconditions
    :universal-preconditions :conditional-effects :derived-predicates
    :action-costs)

  ;; ====================================================================
  ;; FUNCTIONS (for action costs)
  ;; ====================================================================
  (:functions
    (total-cost) - number
    (distance ?from - Space ?to - Space) - number  ; Distance between spaces (via Portal paths: Space->Portal->Space)
  )

  ;; ====================================================================
  ;; TYPES
  ;; ====================================================================
  (:types
    Location
    Space Portal - Location  ; Space: robot can be located, Portal: only passable
    Door Stairs Opening - Portal  ; Portal types: Door (requires open), Stairs/Opening (always passable)
    Robot Hand Artifact
  )

  ;; ====================================================================
  ;; PREDICATES
  ;; ====================================================================
  (:predicates
    ;; Topology
    (hasPathTo ?l1 - Location ?l2 - Location)

    ;; Robot-hand structure
    (hasHand ?r - Robot ?h - Hand)

    ;; Affordances (object capabilities)
    ;; Currently used in json_to_dynamic_ttl.py:
    (Affordance_PickupOneHand ?a - Artifact)
    (Affordance_PickupTwoHands ?a - Artifact)
    (Affordance_Open ?a - Artifact)
    (Affordance_PlaceIn ?a - Artifact)
    (Affordance_PlaceOn ?a - Artifact)
    (Affordance_Power ?a - Artifact)
    (Affordance_Sit ?a - Artifact)
    (Affordance_Eat ?a - Artifact)

    ;; Dynamic state
    (robotIsInSpace ?r - Robot ?l - Space)  ; Robot can only be in Space, not in Door/Stairs/Opening
    (isInSpace ?x - Artifact ?l - Location)
    (isInsideOf ?x - Artifact ?c - Artifact)
    (isOntopOf ?x - Artifact ?y - Artifact)
    (isHeldBy ?x - Artifact ?h - Hand)
    (isON ?a - Artifact)
    (isOpen ?a - Artifact)
    (isLocked ?a - Artifact)  ; Artifact is locked (requires key to open)
    (isOpenDoor ?d - Door)
    (isAdjacentTo ?r - Robot ?x - Artifact)

    ;; Key-Safe relationships
    (hasRequiredKey ?s - Artifact ?k - Artifact)  ; Safe s has required key k (attribute: each safe knows its key)
    (unlocks ?k - Artifact ?s - Artifact)  ; Key k unlocks safe s (bidirectional relationship)
  )

  ;; ====================================================================
  ;; DERIVED PREDICATES
  ;; ====================================================================

  ;; Note: isEmpty conditions are inlined in action preconditions
  ;; isEmpty = (not (exists (?x - Artifact) (isHeldBy ?x ?h)))

  ;; Note: carries conditions are inlined in action preconditions
  ;; carries = (exists (?h - Hand) (and (hasHand ?r ?h) (isHeldBy ?x ?h)))

  ;; Note: isHeldByTwoHands conditions are inlined in action preconditions
  ;; isHeldByTwoHands = (exists (?h1 - Hand ?h2 - Hand) (and (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2)) (isHeldBy ?x ?h1) (isHeldBy ?x ?h2)))

  ;; Note: canManipulate conditions are inlined in action preconditions
  ;; because Fast Downward translate doesn't support derived predicates in preconditions

  ;; ====================================================================
  ;; MOVEMENT
  ;; ====================================================================

  (:action move
    :parameters (?r - Robot ?from - Space ?to - Space)
    :precondition (and
      (robotIsInSpace ?r ?from)
      ; Movement requires a portal (Door/Stairs/Opening) between spaces
      ; Robot moves from Space to Space, passing through a Portal (robot never stays in Portal)
      ; Space -> Portal -> Space path must exist
      (or
        ; Path through a Door (must be open)
        (exists (?d - Door)
          (and (hasPathTo ?from ?d) (hasPathTo ?d ?to) (isOpenDoor ?d)))
        ; Path through Stairs (always passable)
        (exists (?s - Stairs)
          (and (hasPathTo ?from ?s) (hasPathTo ?s ?to)))
        ; Path through Opening (always passable)
        (exists (?o - Opening)
          (and (hasPathTo ?from ?o) (hasPathTo ?o ?to)))))
      ; Note: distance function is used in effect for cost calculation
      ; Problem file must define distance for all Space->Space paths
    :effect (and
      (not (robotIsInSpace ?r ?from))
      (robotIsInSpace ?r ?to)
      (forall (?x - Artifact)
        (when (isAdjacentTo ?r ?x)
          (not (isAdjacentTo ?r ?x))))
      (increase (total-cost) (distance ?from ?to)))
  )

  ;; ====================================================================
  ;; ACCESS (approach artifact)
  ;; ====================================================================

  (:action access
    :parameters (?r - Robot ?x - Artifact ?p - Space)
    :precondition (and
      (robotIsInSpace ?r ?p)
      (not (isAdjacentTo ?r ?x))
      (isInSpace ?x ?p))
    :effect (and
      (forall (?other - Artifact)
        (when (and (not (= ?other ?x)) (isAdjacentTo ?r ?other))
          (not (isAdjacentTo ?r ?other))))
      (isAdjacentTo ?r ?x)
      (forall (?y - Artifact)
        (when (isInsideOf ?y ?x)
          (isAdjacentTo ?r ?y)))
      (forall (?z - Artifact)
        (when (isOntopOf ?z ?x)
          (isAdjacentTo ?r ?z)))
      (increase (total-cost) 1))
  )

  ;; ====================================================================
  ;; DOOR CONTROL
  ;; ====================================================================

  (:action open-door
    :parameters (?r - Robot ?d - Door)
    :precondition (and
      (not (isOpenDoor ?d))
      (exists (?p - Space)
        (and (robotIsInSpace ?r ?p)
             (hasPathTo ?p ?d))))  ; Robot must be in a Space adjacent to the door
    :effect (and
      (isOpenDoor ?d)
      (increase (total-cost) 2))
  )

  (:action close-door
    :parameters (?r - Robot ?d - Door)
    :precondition (and
      (isOpenDoor ?d)
      (exists (?p - Space)
        (and (robotIsInSpace ?r ?p)
             (hasPathTo ?p ?d))))  ; Robot must be in a Space adjacent to the door
    :effect (and
      (not (isOpenDoor ?d))
      (increase (total-cost) 2))
  )

  ;; ====================================================================
  ;; ARTIFACT CONTROL
  ;; ====================================================================

  (:action open
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Open ?a)
      (not (isOpen ?a))  ; Must be closed
      (not (isLocked ?a))  ; Cannot open if locked (must unlock first)
      ; canManipulate conditions: adjacent, not blocked by closed container, not covered
      (isAdjacentTo ?r ?a)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?a ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?a ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?a)))
      ; If artifact requires a key, it must have been unlocked (isLocked is false)
      ; This is already enforced by (not (isLocked ?a)) above
      )
      ;; Note: Artifacts with hasRequiredKey can be opened after unlock-safe removes isLocked
    :effect (and
      (isOpen ?a)
      (increase (total-cost) 2))
  )

  (:action close
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Open ?a)
      (isOpen ?a)  ; Must be open
      (not (isLocked ?a))  ; Cannot close if locked (locked artifacts are always closed)
      ; canManipulate conditions: adjacent, not blocked by closed container, not covered
      (isAdjacentTo ?r ?a)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?a ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?a ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?a))))
    :effect (and
      (not (isOpen ?a))
      (increase (total-cost) 2))
  )

  ;; ====================================================================
  ;; SAFE CONTROL (with key)
  ;; ====================================================================

  (:action unlock-safe
    :parameters (?r - Robot ?s - Artifact ?k - Artifact)
    :precondition (and
      (Affordance_Open ?s)
      (hasRequiredKey ?s ?k)  ; Safe s has required key k (attribute)
      (unlocks ?k ?s)  ; Key k unlocks safe s (bidirectional relationship)
      (isLocked ?s)  ; Must be locked to unlock
      (not (isOpen ?s))  ; Must be closed to unlock (locked safes are always closed)
      ; canManipulate conditions: adjacent, not blocked by closed container, not covered
      (isAdjacentTo ?r ?s)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?s ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?s ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?s)))
      ; Robot must be carrying the key (carries condition inlined)
      (exists (?h - Hand) (and (hasHand ?r ?h) (isHeldBy ?k ?h))))
    :effect (and
      (not (isLocked ?s))  ; Unlock: removes lock only (does not open)
      (increase (total-cost) 1))  ; Lower cost to encourage key-first strategy
  )

  (:action lock-safe
    :parameters (?r - Robot ?s - Artifact ?k - Artifact)
    :precondition (and
      (Affordance_Open ?s)
      (hasRequiredKey ?s ?k)  ; Safe s has required key k (attribute)
      (unlocks ?k ?s)  ; Key k unlocks safe s (bidirectional relationship)
      (not (isLocked ?s))  ; Must be unlocked to lock
      (not (isOpen ?s))  ; Must be closed to lock (can close first, then lock)
      ; canManipulate conditions: adjacent, not blocked by closed container, not covered
      (isAdjacentTo ?r ?s)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?s ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?s ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?s)))
      ; Robot must be carrying the key (carries condition inlined)
      (exists (?h - Hand) (and (hasHand ?r ?h) (isHeldBy ?k ?h))))
    :effect (and
      (isLocked ?s)  ; Lock: adds lock (safe must be closed already)
      (increase (total-cost) 3))
  )

  (:action power-on
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Power ?a)
      (not (isON ?a))
      ; canManipulate conditions: adjacent, not blocked by closed container, not covered
      (isAdjacentTo ?r ?a)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?a ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?a ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?a))))
    :effect (and
      (isON ?a)
      (increase (total-cost) 1))
  )

  (:action power-off
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Power ?a)
      (isON ?a)
      ; canManipulate conditions: adjacent, not blocked by closed container, not covered
      (isAdjacentTo ?r ?a)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?a ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?a ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?a))))
    :effect (and
      (not (isON ?a))
      (increase (total-cost) 1))
  )

  ;; ====================================================================
  ;; PICK (one hand / two hands)
  ;; ====================================================================

  (:action pick-one-hand
    :parameters (?r - Robot ?h - Hand ?x - Artifact)
    :precondition (and
      (hasHand ?r ?h)
      ; Hand must be empty (isEmpty condition inlined)
      (not (exists (?y - Artifact) (isHeldBy ?y ?h)))
      (Affordance_PickupOneHand ?x)
      ; canManipulate conditions: adjacent, not blocked by closed container, not covered
      (isAdjacentTo ?r ?x)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?x ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?x ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?x))))
    :effect (and
      (isHeldBy ?x ?h)
      (forall (?sp - Location) (when (isInSpace ?x ?sp) (not (isInSpace ?x ?sp))))
      (forall (?c - Artifact) (when (isInsideOf ?x ?c) (not (isInsideOf ?x ?c))))
      (forall (?y - Artifact) (when (isOntopOf ?x ?y) (not (isOntopOf ?x ?y))))
      (increase (total-cost) 3))
  )

  (:action pick-two-hands
    :parameters (?r - Robot ?h1 - Hand ?h2 - Hand ?x - Artifact)
    :precondition (and
      (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
      ; Both hands must be empty (isEmpty condition inlined)
      (not (exists (?y1 - Artifact) (isHeldBy ?y1 ?h1)))
      (not (exists (?y2 - Artifact) (isHeldBy ?y2 ?h2)))
      (Affordance_PickupTwoHands ?x)
      ; canManipulate conditions: adjacent, not blocked by closed container, not covered
      (isAdjacentTo ?r ?x)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?x ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?x ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?x))))
    :effect (and
      (isHeldBy ?x ?h1)
      (isHeldBy ?x ?h2)
      (forall (?sp - Location) (when (isInSpace ?x ?sp) (not (isInSpace ?x ?sp))))
      (forall (?c - Artifact) (when (isInsideOf ?x ?c) (not (isInsideOf ?x ?c))))
      (forall (?y - Artifact) (when (isOntopOf ?x ?y) (not (isOntopOf ?x ?y))))
      (increase (total-cost) 5))
  )

  ;; ====================================================================
  ;; PLACE to location
  ;; ====================================================================

  (:action place-to-location-one-hand
    :parameters (?r - Robot ?h - Hand ?x - Artifact ?p - Space)
    :precondition (and
      (hasHand ?r ?h)
      (robotIsInSpace ?r ?p)
      (isHeldBy ?x ?h)
      ; Artifact must not be held by two hands (isHeldByTwoHands condition inlined)
      (not (exists (?h1 - Hand ?h2 - Hand)
        (and (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
             (isHeldBy ?x ?h1) (isHeldBy ?x ?h2)))))
    :effect (and
      (isInSpace ?x ?p)
      (not (isHeldBy ?x ?h))
      (forall (?c - Artifact) (when (isInsideOf ?x ?c) (not (isInsideOf ?x ?c))))
      (forall (?y - Artifact) (when (isOntopOf  ?x ?y) (not (isOntopOf  ?x ?y))))
      (increase (total-cost) 3))
  )

  (:action place-to-location-two-hands
    :parameters (?r - Robot ?h1 - Hand ?h2 - Hand ?x - Artifact ?p - Space)
    :precondition (and
      (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
      (robotIsInSpace ?r ?p)
      (isHeldBy ?x ?h1)
      (isHeldBy ?x ?h2))
    :effect (and
      (isInSpace ?x ?p)
      (not (isHeldBy ?x ?h1))
      (not (isHeldBy ?x ?h2))
      (forall (?c - Artifact) (when (isInsideOf ?x ?c) (not (isInsideOf ?x ?c))))
      (forall (?y - Artifact) (when (isOntopOf  ?x ?y) (not (isOntopOf  ?x ?y))))
      (increase (total-cost) 5))
  )

  ;; ====================================================================
  ;; PLACE IN (container)
  ;; ====================================================================

  (:action place-in-one-hand
    :parameters (?r - Robot ?h - Hand ?x - Artifact ?c - Artifact)
    :precondition (and
      (hasHand ?r ?h)
      (isHeldBy ?x ?h)
      ; Artifact must not be held by two hands (isHeldByTwoHands condition inlined)
      (not (exists (?h1 - Hand ?h2 - Hand)
        (and (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
             (isHeldBy ?x ?h1) (isHeldBy ?x ?h2))))
      (Affordance_PlaceIn ?c)
      (isAdjacentTo ?r ?c)
      (or (not (Affordance_Open ?c)) (isOpen ?c)))
    :effect (and
      (isInsideOf ?x ?c)
      (not (isHeldBy ?x ?h))
      ; Remove old location relationships
      (forall (?sp - Location) (when (isInSpace ?x ?sp) (not (isInSpace ?x ?sp))))
      (forall (?y  - Artifact) (when (isOntopOf ?x ?y) (not (isOntopOf ?x ?y))))
      (forall (?z  - Artifact) (when (isInsideOf ?x ?z) (not (isInsideOf ?x ?z))))
      ; Inherit location from container object
      (forall (?sp - Location) (when (isInSpace ?c ?sp) (isInSpace ?x ?sp)))
      (increase (total-cost) 3))
  )

  (:action place-in-two-hands
    :parameters (?r - Robot ?h1 - Hand ?h2 - Hand ?x - Artifact ?c - Artifact)
    :precondition (and
      (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
      (isHeldBy ?x ?h1)
      (isHeldBy ?x ?h2)
      (Affordance_PlaceIn ?c)
      (isAdjacentTo ?r ?c)
      (or (not (Affordance_Open ?c)) (isOpen ?c)))
    :effect (and
      (isInsideOf ?x ?c)
      (not (isHeldBy ?x ?h1))
      (not (isHeldBy ?x ?h2))
      ; Remove old location relationships
      (forall (?sp - Location) (when (isInSpace ?x ?sp) (not (isInSpace ?x ?sp))))
      (forall (?y  - Artifact) (when (isOntopOf ?x ?y) (not (isOntopOf ?x ?y))))
      (forall (?z  - Artifact) (when (isInsideOf ?x ?z) (not (isInsideOf ?x ?z))))
      ; Inherit location from container object
      (forall (?sp - Location) (when (isInSpace ?c ?sp) (isInSpace ?x ?sp)))
      (increase (total-cost) 5))
  )

  ;; ====================================================================
  ;; PLACE ON (support surface)
  ;; ====================================================================

  (:action place-on-one-hand
    :parameters (?r - Robot ?h - Hand ?x - Artifact ?y - Artifact)
    :precondition (and
      (hasHand ?r ?h)
      (isHeldBy ?x ?h)
      ; Artifact must not be held by two hands (isHeldByTwoHands condition inlined)
      (not (exists (?h1 - Hand ?h2 - Hand)
        (and (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
             (isHeldBy ?x ?h1) (isHeldBy ?x ?h2))))
      (Affordance_PlaceOn ?y)
      (isAdjacentTo ?r ?y))
    :effect (and
      (isOntopOf ?x ?y)
      (not (isHeldBy ?x ?h))
      ; Remove old location relationships
      (forall (?sp - Location) (when (isInSpace ?x ?sp) (not (isInSpace ?x ?sp))))
      (forall (?z  - Artifact) (when (isInsideOf ?x ?z) (not (isInsideOf ?x ?z))))
      (forall (?z  - Artifact) (when (isOntopOf  ?x ?z) (not (isOntopOf  ?x ?z))))
      ; Inherit location from surface object
      (forall (?sp - Location) (when (isInSpace ?y ?sp) (isInSpace ?x ?sp)))
      (increase (total-cost) 3))
  )

  (:action place-on-two-hands
    :parameters (?r - Robot ?h1 - Hand ?h2 - Hand ?x - Artifact ?y - Artifact)
    :precondition (and
      (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
      (isHeldBy ?x ?h1)
      (isHeldBy ?x ?h2)
      (Affordance_PlaceOn ?y)
      (isAdjacentTo ?r ?y))
    :effect (and
      (isOntopOf ?x ?y)
      (not (isHeldBy ?x ?h1))
      (not (isHeldBy ?x ?h2))
      ; Remove old location relationships
      (forall (?sp - Location) (when (isInSpace ?x ?sp) (not (isInSpace ?x ?sp))))
      (forall (?z  - Artifact) (when (isInsideOf ?x ?z) (not (isInsideOf ?x ?z))))
      (forall (?z  - Artifact) (when (isOntopOf  ?x ?z) (not (isOntopOf  ?x ?z))))
      ; Inherit location from surface object
      (forall (?sp - Location) (when (isInSpace ?y ?sp) (isInSpace ?x ?sp)))
      (increase (total-cost) 5))
  )

  ;; ====================================================================
  ;; CONSUMPTION ACTIONS
  ;; ====================================================================

  (:action eat
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Eat ?a)
      ; Robot must be adjacent to the food
      (isAdjacentTo ?r ?a)
      ; Food must not be inside a closed container
      (or
        (not (exists (?c - Artifact) (isInsideOf ?a ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?a ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      ; Food must not be covered
      (not (exists (?z - Artifact) (isOntopOf ?z ?a)))
      ; Food must be accessible (not held by robot, or if held, can be eaten directly)
      (or
        (not (exists (?h - Hand) (isHeldBy ?a ?h)))
        (exists (?h - Hand) (and (hasHand ?r ?h) (isHeldBy ?a ?h)))))
    :effect (and
      ; Remove food from space/container/hand
      (forall (?sp - Location) (when (isInSpace ?a ?sp) (not (isInSpace ?a ?sp))))
      (forall (?c - Artifact) (when (isInsideOf ?a ?c) (not (isInsideOf ?a ?c))))
      (forall (?h - Hand) (when (isHeldBy ?a ?h) (not (isHeldBy ?a ?h))))
      (forall (?y - Artifact) (when (isOntopOf ?a ?y) (not (isOntopOf ?a ?y))))
      (increase (total-cost) 2))
  )

  ;; ====================================================================
  ;; INTERACTION ACTIONS
  ;; ====================================================================

  (:action sit
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Sit ?a)
      ; Robot must be adjacent to the seat
      (isAdjacentTo ?r ?a)
      ; Seat must be accessible
      (or
        (not (exists (?c - Artifact) (isInsideOf ?a ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?a ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?a))))
    :effect (and
      ; Robot sits on the artifact (can be represented as isOntopOf robot artifact, but robot is not Artifact type)
      ; For now, just maintain adjacency (sitting doesn't change robot location)
      (increase (total-cost) 1))
  )

  ;; ====================================================================
  ;; COOKING ACTIONS
  ;; ====================================================================

  (:action cook
    :parameters (?r - Robot ?food - Artifact ?oven - Artifact)
    :precondition (and
      (Affordance_Power ?oven)
      (isON ?oven)  ; Oven must be on
      ; Food must be held by robot or accessible
      (or
        (exists (?h - Hand) (and (hasHand ?r ?h) (isHeldBy ?food ?h)))
        (and (isAdjacentTo ?r ?food)
             (or
               (not (exists (?c - Artifact) (isInsideOf ?food ?c)))
               (exists (?c - Artifact)
                 (and (isInsideOf ?food ?c)
                      (or (not (Affordance_Open ?c)) (isOpen ?c)))))
             (not (exists (?z - Artifact) (isOntopOf ?z ?food)))))
      ; Robot must be adjacent to oven
      (isAdjacentTo ?r ?oven)
      ; Oven must be open (to put food in)
      (or (not (Affordance_Open ?oven)) (isOpen ?oven)))
    :effect (and
      ; Food goes inside oven
      (isInsideOf ?food ?oven)
      ; Remove food from previous location/hand
      (forall (?sp - Location) (when (isInSpace ?food ?sp) (not (isInSpace ?food ?sp))))
      (forall (?h - Hand) (when (isHeldBy ?food ?h) (not (isHeldBy ?food ?h))))
      (forall (?y - Artifact) (when (isOntopOf ?food ?y) (not (isOntopOf ?food ?y))))
      ; Food inherits oven's location
      (forall (?sp - Location) (when (isInSpace ?oven ?sp) (isInSpace ?food ?sp)))
      (increase (total-cost) 3))
  )

  (:action take-out-from-oven
    :parameters (?r - Robot ?food - Artifact ?oven - Artifact ?h - Hand)
    :precondition (and
      (hasHand ?r ?h)
      ; Hand must be empty
      (not (exists (?y - Artifact) (isHeldBy ?y ?h)))
      ; Food must be inside oven
      (isInsideOf ?food ?oven)
      ; Oven must be open
      (or (not (Affordance_Open ?oven)) (isOpen ?oven))
      ; Robot must be adjacent to oven
      (isAdjacentTo ?r ?oven))
    :effect (and
      ; Food is now held by hand
      (isHeldBy ?food ?h)
      ; Remove food from oven
      (not (isInsideOf ?food ?oven))
      ; Remove food from oven's location
      (forall (?sp - Location) (when (isInSpace ?food ?sp) (not (isInSpace ?food ?sp))))
      (increase (total-cost) 2))
  )

  ;; ====================================================================
  ;; POURING ACTIONS (for liquids)
  ;; ====================================================================

  (:action pour
    :parameters (?r - Robot ?container - Artifact ?target - Artifact ?h - Hand)
    :precondition (and
      (hasHand ?r ?h)
      ; Container must be held
      (isHeldBy ?container ?h)
      ; Target must have PlaceIn affordance (can receive liquid)
      (Affordance_PlaceIn ?target)
      ; Target must be open
      (or (not (Affordance_Open ?target)) (isOpen ?target))
      ; Robot must be adjacent to target
      (isAdjacentTo ?r ?target)
      ; Container must be open (to pour)
      (or (not (Affordance_Open ?container)) (isOpen ?container)))
    :effect (and
      ; Container contents go into target (simplified: container becomes empty)
      ; In a more detailed model, we'd track liquid amounts
      (increase (total-cost) 2))
  )

  ;; ====================================================================
  ;; MANIPULATION ACTIONS
  ;; ====================================================================

  (:action wash
    :parameters (?r - Robot ?item - Artifact ?sink - Artifact)
    :precondition (and
      ; Item must be held or accessible
      (or
        (exists (?h - Hand) (and (hasHand ?r ?h) (isHeldBy ?item ?h)))
        (and (isAdjacentTo ?r ?item)
             (or
               (not (exists (?c - Artifact) (isInsideOf ?item ?c)))
               (exists (?c - Artifact)
                 (and (isInsideOf ?item ?c)
                      (or (not (Affordance_Open ?c)) (isOpen ?c)))))
             (not (exists (?z - Artifact) (isOntopOf ?z ?item)))))
      ; Robot must be adjacent to sink
      (isAdjacentTo ?r ?sink)
      ; Sink must be accessible (if it's in a container, container must be open)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?sink ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?sink ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?sink)))
      ; TODO: Uncomment when Affordance_Wash is added to json_to_dynamic_ttl.py
      ; (Affordance_Wash ?sink))
    :effect (and
      ; Item is now clean (could add a "isClean" predicate if needed)
      ; For now, just maintain item's state
      (increase (total-cost) 3))
  )

  (:action cut
    :parameters (?r - Robot ?item - Artifact ?tool - Artifact ?h - Hand)
    :precondition (and
      (hasHand ?r ?h)
      ; Tool must be held
      (isHeldBy ?tool ?h)
      ; TODO: Uncomment when Affordance_Cut is added to json_to_dynamic_ttl.py
      ; (Affordance_Cut ?tool)
      ; Item must be accessible
      (isAdjacentTo ?r ?item)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?item ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?item ?c)
               (or (not (Affordance_Open ?c)) (isOpen ?c)))))
      (not (exists (?z - Artifact) (isOntopOf ?z ?item))))
    :effect (and
      ; Item is now cut (could add a "isCut" predicate if needed)
      ; For now, just maintain item's state
      (increase (total-cost) 2))
  )

  (:action mix
    :parameters (?r - Robot ?container - Artifact ?h - Hand)
    :precondition (and
      (hasHand ?r ?h)
      ; Container must be held or accessible
      (or
        (isHeldBy ?container ?h)
        (and (isAdjacentTo ?r ?container)
             (or
               (not (exists (?c - Artifact) (isInsideOf ?container ?c)))
               (exists (?c - Artifact)
                 (and (isInsideOf ?container ?c)
                      (or (not (Affordance_Open ?c)) (isOpen ?c)))))
             (not (exists (?z - Artifact) (isOntopOf ?z ?container)))))
      ; Container must be open (to mix contents)
      (or (not (Affordance_Open ?container)) (isOpen ?container))
      ; TODO: Uncomment when Affordance_Mix is added to json_to_dynamic_ttl.py
      ; (Affordance_Mix ?container))
    :effect (and
      ; Contents are now mixed (could add a "isMixed" predicate if needed)
      ; For now, just maintain container's state
      (increase (total-cost) 2))
  )

  (:action drink
    :parameters (?r - Robot ?container - Artifact ?h - Hand)
    :precondition (and
      (hasHand ?r ?h)
      ; Container must be held
      (isHeldBy ?container ?h)
      ; Container must be open (to drink from)
      (or (not (Affordance_Open ?container)) (isOpen ?container))
      ; TODO: Uncomment when Affordance_Drink is added to json_to_dynamic_ttl.py
      ; Or use Affordance_Eat if drinkable items share the same affordance
      ; (Affordance_Drink ?container))
    :effect (and
      ; Container is now empty (could add a "isEmpty" predicate for containers if needed)
      ; For now, just maintain container's state
      (increase (total-cost) 2))
  )

  ;; ====================================================================
  ;; COMPOSITE ACTIONS (combining multiple steps)
  ;; ====================================================================

  (:action move-with-object
    :parameters (?r - Robot ?from - Space ?to - Space ?obj - Artifact ?h - Hand)
    :precondition (and
      (robotIsInSpace ?r ?from)
      (hasHand ?r ?h)
      ; Object must be held
      (isHeldBy ?obj ?h)
      ; Movement requires a portal (same as regular move)
      (or
        (exists (?d - Door)
          (and (hasPathTo ?from ?d) (hasPathTo ?d ?to) (isOpenDoor ?d)))
        (exists (?s - Stairs)
          (and (hasPathTo ?from ?s) (hasPathTo ?s ?to)))
        (exists (?o - Opening)
          (and (hasPathTo ?from ?o) (hasPathTo ?o ?to)))))
    :effect (and
      (not (robotIsInSpace ?r ?from))
      (robotIsInSpace ?r ?to)
      ; Object moves with robot (maintain isHeldBy)
      ; Remove adjacency to other objects
      (forall (?x - Artifact)
        (when (isAdjacentTo ?r ?x)
          (not (isAdjacentTo ?r ?x))))
      ; Cost = distance + 1 (slightly more expensive than regular move)
      ; Note: PDDL doesn't support + operator in increase, so we use distance + 1 as a fixed cost
      ; For simplicity, we'll use a fixed cost of 1 more than the distance
      ; In practice, this means move-with-object costs (distance + 1)
      (increase (total-cost) (distance ?from ?to))
      (increase (total-cost) 1))
  )

  ;; ====================================================================
  ;; ADDITIONAL AFFORDANCES (for new actions - not yet in json_to_dynamic_ttl.py)
  ;; ====================================================================
  ;; TODO: Add these to json_to_dynamic_ttl.py mapping if needed:
  ;; These affordances are commented out because they are not yet mapped in json_to_dynamic_ttl.py
  ;; Uncomment the affordance definitions below and add corresponding mappings in json_to_dynamic_ttl.py
  ;;
  ;; (:predicates
  ;;   (Affordance_Wash ?a - Artifact)      ; For wash action (sink/faucet)
  ;;   (Affordance_Cut ?a - Artifact)       ; For cut action (cutting tool like knife)
  ;;   (Affordance_Mix ?a - Artifact)       ; For mix action (mixable container like bowl)
  ;;   (Affordance_Drink ?a - Artifact)     ; For drink action (drinkable container, or use Affordance_Eat)
  ;; )
)
