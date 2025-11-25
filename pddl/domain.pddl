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
    (distance ?from - Location ?to - Location) - number
  )

  ;; ====================================================================
  ;; TYPES
  ;; ====================================================================
  (:types
    Location
    Space Door Stairs Opening - Location
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
    (Affordance_PickupOneHand ?a - Artifact)
    (Affordance_PickupTwoHands ?a - Artifact)
    (Affordance_Open ?a - Artifact)
    (Affordance_PlaceIn ?a - Artifact)
    (Affordance_PlaceOn ?a - Artifact)
    (Affordance_Power ?a - Artifact)
    (Affordance_Sit ?a - Artifact)
    (Affordance_Eat ?a - Artifact)

    ;; Dynamic state - Base predicates
    (robotIsInSpace ?r - Robot ?l - Location)
    (artifactIsOnFloorOf ?x - Artifact ?l - Location)
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

    ;; Derived predicates (computed automatically)
    (isEmpty ?h - Hand)
    (carries ?r - Robot ?x - Artifact)
    (isHeldByTwoHands ?r - Robot ?x - Artifact)
    (artifactIsInSpace ?x - Artifact ?l - Location)
    (canActuate ?r - Robot ?x - Artifact)
    (canManipulate ?r - Robot ?x - Artifact)
  )

  ;; ====================================================================
  ;; DERIVED PREDICATES
  ;; ====================================================================

  ;; Hand is empty if no artifact is held by it
  (:derived (isEmpty ?h - Hand)
    (not (exists (?x - Artifact) (isHeldBy ?x ?h)))
  )

  ;; Robot is carrying artifact with at least one hand
  (:derived (carries ?r - Robot ?x - Artifact)
    (exists (?h - Hand) (and (hasHand ?r ?h) (isHeldBy ?x ?h)))
  )

  ;; Robot is holding artifact with both hands
  (:derived (isHeldByTwoHands ?r - Robot ?x - Artifact)
    (exists (?h1 - Hand ?h2 - Hand)
      (and (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
           (isHeldBy ?x ?h1) (isHeldBy ?x ?h2)))
  )

  ;; Artifact is in space if:
  ;; - On floor of space
  ;; - Inside container in space
  ;; - On surface in space
  ;; - Carried by robot in space
  (:derived (artifactIsInSpace ?x - Artifact ?l - Location)
    (or
      ; Base: directly on floor
      (artifactIsOnFloorOf ?x ?l)

      ; Inside container in space
      (exists (?c - Artifact)
        (and (isInsideOf ?x ?c) (artifactIsInSpace ?c ?l)))

      ; On surface in space
      (exists (?y - Artifact)
        (and (isOntopOf ?x ?y) (artifactIsInSpace ?y ?l)))

      ; Carried by robot in space
      (exists (?r - Robot)
        (and (carries ?r ?x) (robotIsInSpace ?r ?l)))
    )
  )

  ;; Robot can actuate artifact (open/close, power) if:
  ;; - Adjacent to it
  ;; - Not blocked by closed container
  (:derived (canActuate ?r - Robot ?x - Artifact)
    (and
      (isAdjacentTo ?r ?x)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?x ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?x ?c)
               (or
                 (not (Affordance_Open ?c))  ; No open/close → always accessible
                 (isOpen ?c))))))             ; Has open/close → must be open
  )

  ;; Robot can manipulate artifact (pick/place) if:
  ;; - Adjacent to it
  ;; - Not blocked by closed container
  ;; - Not covered by another object
  (:derived (canManipulate ?r - Robot ?x - Artifact)
    (and
      (isAdjacentTo ?r ?x)
      (or
        (not (exists (?c - Artifact) (isInsideOf ?x ?c)))
        (exists (?c - Artifact)
          (and (isInsideOf ?x ?c)
               (or
                 (not (Affordance_Open ?c))  ; No open/close → always accessible
                 (isOpen ?c)))))              ; Has open/close → must be open
      (not (exists (?z - Artifact) (isOntopOf ?z ?x)))
    )
  )

  ;; ====================================================================
  ;; MOVEMENT
  ;; ====================================================================

  (:action move
    :parameters (?r - Robot ?from - Location ?to - Location)
    :precondition (and
      (robotIsInSpace ?r ?from)
      (hasPathTo ?from ?to)
      (or
        (not (exists (?d - Door) (= ?from ?d)))
        (exists (?d - Door) (and (= ?from ?d) (isOpenDoor ?d)))))
    :effect (and
      (not (robotIsInSpace ?r ?from))
      (robotIsInSpace ?r ?to)
      ; Clear all adjacency when moving
      (forall (?x - Artifact)
        (when (isAdjacentTo ?r ?x)
          (not (isAdjacentTo ?r ?x))))
      ; Carried artifacts' artifactIsInSpace is automatically updated via derived predicate!
      (increase (total-cost) (distance ?from ?to)))
  )

  ;; ====================================================================
  ;; ACCESS (approach artifact)
  ;; ====================================================================

  (:action access
    :parameters (?r - Robot ?x - Artifact ?p - Location)
    :precondition (and
      (robotIsInSpace ?r ?p)
      (not (isAdjacentTo ?r ?x))
      (artifactIsInSpace ?x ?p))
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
      (robotIsInSpace ?r ?d))
    :effect (and
      (isOpenDoor ?d)
      (increase (total-cost) 2))
  )

  (:action close-door
    :parameters (?r - Robot ?d - Door)
    :precondition (and
      (isOpenDoor ?d)
      (robotIsInSpace ?r ?d))
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
      (not (isOpen ?a))
      (not (isLocked ?a))  ; Cannot open if locked (must unlock first)
      (canActuate ?r ?a))
    :effect (and
      (isOpen ?a)
      (increase (total-cost) 2))
  )

  (:action close
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Open ?a)
      (isOpen ?a)
      (not (isLocked ?a))  ; Cannot close if locked (locked artifacts are always closed)
      (canActuate ?r ?a))
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
      (canActuate ?r ?s)
      (carries ?r ?k))  ; Robot must be carrying the key
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
      (canActuate ?r ?s)
      (carries ?r ?k))  ; Robot must be carrying the key
    :effect (and
      (isLocked ?s)  ; Lock: adds lock (safe must be closed already)
      (increase (total-cost) 3))
  )

  (:action power-on
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Power ?a)
      (not (isON ?a))
      (canActuate ?r ?a))
    :effect (and
      (isON ?a)
      (increase (total-cost) 1))
  )

  (:action power-off
    :parameters (?r - Robot ?a - Artifact)
    :precondition (and
      (Affordance_Power ?a)
      (isON ?a)
      (canActuate ?r ?a))
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
      (isEmpty ?h)
      (Affordance_PickupOneHand ?x)
      (canManipulate ?r ?x))
    :effect (and
      (isHeldBy ?x ?h)
      ; Remove old location relationships (artifactIsInSpace auto-updated via derived)
      (forall (?l - Location) (when (artifactIsOnFloorOf ?x ?l) (not (artifactIsOnFloorOf ?x ?l))))
      (forall (?c - Artifact) (when (isInsideOf ?x ?c) (not (isInsideOf ?x ?c))))
      (forall (?y - Artifact) (when (isOntopOf ?x ?y) (not (isOntopOf ?x ?y))))
      (increase (total-cost) 3))
  )

  (:action pick-two-hands
    :parameters (?r - Robot ?h1 - Hand ?h2 - Hand ?x - Artifact)
    :precondition (and
      (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
      (isEmpty ?h1) (isEmpty ?h2)
      (Affordance_PickupTwoHands ?x)
      (canManipulate ?r ?x))
    :effect (and
      (isHeldBy ?x ?h1)
      (isHeldBy ?x ?h2)
      ; Remove old location relationships (artifactIsInSpace auto-updated via derived)
      (forall (?l - Location) (when (artifactIsOnFloorOf ?x ?l) (not (artifactIsOnFloorOf ?x ?l))))
      (forall (?c - Artifact) (when (isInsideOf ?x ?c) (not (isInsideOf ?x ?c))))
      (forall (?y - Artifact) (when (isOntopOf ?x ?y) (not (isOntopOf ?x ?y))))
      (increase (total-cost) 5))
  )

  ;; ====================================================================
  ;; PLACE to location
  ;; ====================================================================

  (:action place-to-location-one-hand
    :parameters (?r - Robot ?h - Hand ?x - Artifact ?p - Location)
    :precondition (and
      (hasHand ?r ?h)
      (robotIsInSpace ?r ?p)
      (isHeldBy ?x ?h)
      (not (isHeldByTwoHands ?r ?x)))
    :effect (and
      (artifactIsOnFloorOf ?x ?p)
      (not (isHeldBy ?x ?h))
      ; Remove old relationships (artifactIsInSpace auto-updated via derived)
      (forall (?c - Artifact) (when (isInsideOf ?x ?c) (not (isInsideOf ?x ?c))))
      (forall (?y - Artifact) (when (isOntopOf  ?x ?y) (not (isOntopOf  ?x ?y))))
      (increase (total-cost) 3))
  )

  (:action place-to-location-two-hands
    :parameters (?r - Robot ?h1 - Hand ?h2 - Hand ?x - Artifact ?p - Location)
    :precondition (and
      (hasHand ?r ?h1) (hasHand ?r ?h2) (not (= ?h1 ?h2))
      (robotIsInSpace ?r ?p)
      (isHeldBy ?x ?h1)
      (isHeldBy ?x ?h2))
    :effect (and
      (artifactIsOnFloorOf ?x ?p)
      (not (isHeldBy ?x ?h1))
      (not (isHeldBy ?x ?h2))
      ; Remove old relationships (artifactIsInSpace auto-updated via derived)
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
      (not (isHeldByTwoHands ?r ?x))
      (Affordance_PlaceIn ?c)
      (isAdjacentTo ?r ?c)
      (or (not (Affordance_Open ?c)) (isOpen ?c)))
    :effect (and
      (isInsideOf ?x ?c)
      (not (isHeldBy ?x ?h))
      ; Remove old location relationships (artifactIsInSpace auto-updated via derived)
      (forall (?l  - Location) (when (artifactIsOnFloorOf ?x ?l) (not (artifactIsOnFloorOf ?x ?l))))
      (forall (?y  - Artifact) (when (isOntopOf ?x ?y) (not (isOntopOf ?x ?y))))
      (forall (?z  - Artifact) (when (isInsideOf ?x ?z) (not (isInsideOf ?x ?z))))
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
      ; Remove old location relationships (artifactIsInSpace auto-updated via derived)
      (forall (?l  - Location) (when (artifactIsOnFloorOf ?x ?l) (not (artifactIsOnFloorOf ?x ?l))))
      (forall (?y  - Artifact) (when (isOntopOf ?x ?y) (not (isOntopOf ?x ?y))))
      (forall (?z  - Artifact) (when (isInsideOf ?x ?z) (not (isInsideOf ?x ?z))))
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
      (not (isHeldByTwoHands ?r ?x))
      (Affordance_PlaceOn ?y)
      (isAdjacentTo ?r ?y))
    :effect (and
      (isOntopOf ?x ?y)
      (not (isHeldBy ?x ?h))
      ; Remove old location relationships (artifactIsInSpace auto-updated via derived)
      (forall (?l  - Location) (when (artifactIsOnFloorOf ?x ?l) (not (artifactIsOnFloorOf ?x ?l))))
      (forall (?z  - Artifact) (when (isInsideOf ?x ?z) (not (isInsideOf ?x ?z))))
      (forall (?z  - Artifact) (when (isOntopOf  ?x ?z) (not (isOntopOf  ?x ?z))))
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
      ; Remove old location relationships (artifactIsInSpace auto-updated via derived)
      (forall (?l  - Location) (when (artifactIsOnFloorOf ?x ?l) (not (artifactIsOnFloorOf ?x ?l))))
      (forall (?z  - Artifact) (when (isInsideOf ?x ?z) (not (isInsideOf ?x ?z))))
      (forall (?z  - Artifact) (when (isOntopOf  ?x ?z) (not (isOntopOf  ?x ?z))))
      (increase (total-cost) 5))
  )
)
