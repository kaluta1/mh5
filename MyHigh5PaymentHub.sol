// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal ERC20 interface with the functions this contract needs.
interface IERC20Minimal {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @title MyHigh5PaymentHub
/// @notice Generic payment contract for MyHigh5 order-based payments.
/// @dev The current backend/frontend already work with:
///      - payToken(bytes32 orderId, address token, uint256 amount)
///      - payNative(bytes32 orderId)
///      - PaymentReceived(orderId, payer, amount, token)
///
///      One backend order can represent payment for the caller, for another user,
///      or for multiple recipients. The on-chain contract only needs to secure the
///      money flow and emit a verifiable order event.
contract MyHigh5PaymentHub {
    error NotOwner();
    error NotOperator();
    error ZeroAddress();
    error InvalidAmount();
    error InvalidOrderId();
    error UnsupportedToken();
    error OrderAlreadyPaid();
    error PaymentNotFound();
    error RefundExceedsPaidAmount();
    error TransferFailed();
    error DirectNativeTransferNotAllowed();
    error ReceivedAmountMismatch();
    error ReentrancyBlocked();

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event OperatorUpdated(address indexed operator, bool allowed);
    event TreasuryUpdated(address indexed previousTreasury, address indexed newTreasury);
    event AcceptedTokenUpdated(address indexed token, bool accepted);

    /// @dev Keep this event shape compatible with the current backend verifier.
    event PaymentReceived(
        bytes32 indexed orderId,
        address indexed payer,
        uint256 amount,
        address token
    );

    event PaymentRefunded(
        bytes32 indexed orderId,
        address indexed recipient,
        uint256 amount,
        address token
    );

    event TreasuryWithdrawal(address indexed token, address indexed treasury, uint256 amount);

    struct PaymentRecord {
        address payer;
        address token;
        uint256 amount;
        uint256 refundedAmount;
        uint64 paidAt;
    }

    address public owner;
    address public treasury;

    mapping(address => bool) public operators;
    mapping(address => bool) public acceptedTokens;
    mapping(bytes32 => PaymentRecord) public payments;

    uint256 private _reentrancyLock;

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyOwnerOrOperator() {
        if (msg.sender != owner && !operators[msg.sender]) revert NotOperator();
        _;
    }

    modifier nonReentrant() {
        if (_reentrancyLock == 1) revert ReentrancyBlocked();
        _reentrancyLock = 1;
        _;
        _reentrancyLock = 0;
    }

    constructor(address _treasury) {
        if (_treasury == address(0)) revert ZeroAddress();

        owner = msg.sender;
        treasury = _treasury;

        emit OwnershipTransferred(address(0), msg.sender);
        emit TreasuryUpdated(address(0), _treasury);
    }

    receive() external payable {
        revert DirectNativeTransferNotAllowed();
    }

    fallback() external payable {
        revert DirectNativeTransferNotAllowed();
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();

        address previousOwner = owner;
        owner = newOwner;

        emit OwnershipTransferred(previousOwner, newOwner);
    }

    function setTreasury(address newTreasury) external onlyOwner {
        if (newTreasury == address(0)) revert ZeroAddress();

        address previousTreasury = treasury;
        treasury = newTreasury;

        emit TreasuryUpdated(previousTreasury, newTreasury);
    }

    function setOperator(address operator, bool allowed) external onlyOwner {
        if (operator == address(0)) revert ZeroAddress();

        operators[operator] = allowed;
        emit OperatorUpdated(operator, allowed);
    }

    function setAcceptedToken(address token, bool accepted) external onlyOwner {
        if (token == address(0)) revert ZeroAddress();

        acceptedTokens[token] = accepted;
        emit AcceptedTokenUpdated(token, accepted);
    }

    /// @notice Pay with the chain native token. Included for future flexibility.
    /// @dev Current backend verification flow is built around ERC20 USDT payments.
    function payNative(bytes32 orderId) external payable nonReentrant {
        if (msg.value == 0) revert InvalidAmount();

        _recordPayment(orderId, msg.sender, address(0), msg.value);
    }

    /// @notice Pay with an accepted ERC20 token such as BSC USDT.
    /// @dev This is the function your current frontend already calls.
    function payToken(bytes32 orderId, address token, uint256 amount) external nonReentrant {
        if (!acceptedTokens[token]) revert UnsupportedToken();
        if (amount == 0) revert InvalidAmount();

        _takeExactTokenAmount(token, msg.sender, amount);
        _recordPayment(orderId, msg.sender, token, amount);
    }

    /// @notice Refund all or part of a payment.
    /// @param recipient If zero, refund goes back to the original payer.
    /// @param amount If zero, refund the full remaining refundable balance.
    function refund(bytes32 orderId, address recipient, uint256 amount)
        external
        onlyOwnerOrOperator
        nonReentrant
    {
        PaymentRecord storage payment = payments[orderId];
        if (payment.paidAt == 0) revert PaymentNotFound();

        address refundRecipient = recipient == address(0) ? payment.payer : recipient;
        uint256 remaining = payment.amount - payment.refundedAmount;
        uint256 refundAmount = amount == 0 ? remaining : amount;

        if (refundAmount == 0) revert InvalidAmount();
        if (refundAmount > remaining) revert RefundExceedsPaidAmount();

        payment.refundedAmount += refundAmount;

        if (payment.token == address(0)) {
            _safeTransferNative(refundRecipient, refundAmount);
        } else {
            _safeTransferToken(payment.token, refundRecipient, refundAmount);
        }

        emit PaymentRefunded(orderId, refundRecipient, refundAmount, payment.token);
    }

    /// @notice Withdraw ERC20 funds accumulated in the contract to the treasury.
    function withdrawToken(address token, uint256 amount) external onlyOwner nonReentrant {
        if (token == address(0)) revert ZeroAddress();
        if (amount == 0) revert InvalidAmount();

        _safeTransferToken(token, treasury, amount);
        emit TreasuryWithdrawal(token, treasury, amount);
    }

    /// @notice Withdraw native funds accumulated in the contract to the treasury.
    function withdrawNative(uint256 amount) external onlyOwner nonReentrant {
        if (amount == 0) revert InvalidAmount();

        _safeTransferNative(treasury, amount);
        emit TreasuryWithdrawal(address(0), treasury, amount);
    }

    function refundableAmount(bytes32 orderId) external view returns (uint256) {
        PaymentRecord memory payment = payments[orderId];
        if (payment.paidAt == 0) return 0;
        return payment.amount - payment.refundedAmount;
    }

    function paymentExists(bytes32 orderId) external view returns (bool) {
        return payments[orderId].paidAt != 0;
    }

    function _recordPayment(bytes32 orderId, address payer, address token, uint256 amount) internal {
        if (orderId == bytes32(0)) revert InvalidOrderId();
        if (payments[orderId].paidAt != 0) revert OrderAlreadyPaid();

        payments[orderId] = PaymentRecord({
            payer: payer,
            token: token,
            amount: amount,
            refundedAmount: 0,
            paidAt: uint64(block.timestamp)
        });

        emit PaymentReceived(orderId, payer, amount, token);
    }

    function _takeExactTokenAmount(address token, address from, uint256 amount) internal {
        uint256 balanceBefore = IERC20Minimal(token).balanceOf(address(this));
        _safeTransferFromToken(token, from, address(this), amount);
        uint256 balanceAfter = IERC20Minimal(token).balanceOf(address(this));

        if (balanceAfter - balanceBefore != amount) revert ReceivedAmountMismatch();
    }

    function _safeTransferNative(address to, uint256 amount) internal {
        (bool success, ) = payable(to).call{value: amount}("");
        if (!success) revert TransferFailed();
    }

    function _safeTransferToken(address token, address to, uint256 amount) internal {
        (bool success, bytes memory data) =
            token.call(abi.encodeWithSelector(IERC20Minimal.transfer.selector, to, amount));

        if (!success || (data.length != 0 && !abi.decode(data, (bool)))) {
            revert TransferFailed();
        }
    }

    function _safeTransferFromToken(address token, address from, address to, uint256 amount) internal {
        (bool success, bytes memory data) =
            token.call(abi.encodeWithSelector(IERC20Minimal.transferFrom.selector, from, to, amount));

        if (!success || (data.length != 0 && !abi.decode(data, (bool)))) {
            revert TransferFailed();
        }
    }
}
