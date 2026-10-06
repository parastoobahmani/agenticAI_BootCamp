On branch Parastoo

## The architecture for : Problem 2 --> Section 2: Human Approval and Correct Execution.

DRAFT
|
|
PENDING_APPROVAL
| 
|----------------|
|                |  
|                |
APPROVED        REJECTED
|
|
VALIDATING
|
|--- stale --> INVALIDATED
|
|--- invalid --> FAILED
| 
| 
EXECUTING
|
|--- already_done --> COMPLETED
|
|--- error --> FAILED
|
COMPLETED

## ---------------------------------

LLM
|
| 
Proposal
|
Human
|
|-- reject ----> STOP
|
|-- edit --> new proposal -> approve
|
|--- approve
        |
Pre-execution validation
        |
        |-- stale --> STOP
        |
        |-- invalid -> STOP
        |
Idempotency check
        |
        |-- already done -> return previous result
        |
Actual tool