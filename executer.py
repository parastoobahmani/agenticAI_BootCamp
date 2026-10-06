def execute(self, proposal_id: str):

    proposal = self.store.get_proposal(proposal_id)
    approval = self.store.get_approval(proposal_id)

    if proposal is None:
        raise ExecutionBlocked("UNKNOWN_PROPOSAL")

    if approval is None:
        raise ExecutionBlocked("NO_APPROVAL")

    # Re-check everything immediately before execution
    action = self.validate_before_execution(
        proposal,
        approval,
    )

    idempotency_key = make_idempotency_key(
        proposal,
        approval,
    )

    existing = self.store.get_action_result(idempotency_key)

    if existing:
        return existing

    proposal.status = ProposalStatus.EXECUTING
    self.store.save_proposal(proposal)

    try:
        result = self.executor.execute(
            action=action,
            idempotency_key=idempotency_key,
        )

        self.store.save_action_result(
            idempotency_key=idempotency_key,
            result=result,
        )

        proposal.status = ProposalStatus.COMPLETED
        self.store.save_proposal(proposal)

        return result

    except Exception as exc:

        proposal.status = ProposalStatus.FAILED
        self.store.save_proposal(proposal)

        self.store.log_event(
            case_id=proposal.case_id,
            event_type="execution_failed",
            details={
                "proposal_id": proposal.proposal_id,
                "error_type": type(exc).__name__,
            },
        )

        raise