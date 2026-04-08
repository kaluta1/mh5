// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal ERC20 interface with the functions this contract needs.
interface IERC20Minimal {
    function balanceOf(address account) external view returns (uint256);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @title MyHigh5PaymentHub
/// @notice Generic payment contract for MyHigh5 order-based payments.
/// @dev Funds go directly to `treasury` on each payment (no custodial balance, no owner withdraw).
///      Backend/frontend use:
///      - payToken(bytes32 orderId, address token, uint256 amount)
///      - payNative(bytes32 orderId)
///      - PaymentReceived(orderId, payer, amount, token)
///
///      One backend order can represent payment for the caller, for another user,
///      or for multiple recipients. The on-chain contract secures the flow and emits a verifiable event.
contract MyHigh5PaymentHub {
    error NotOwner();
    error ZeroAddress();
    error InvalidAmount();
    error InvalidOrderId();
    error UnsupportedToken();
    error OrderAlreadyPaid();
    error TransferFailed();
    error DirectNativeTransferNotAllowed();
    error ReceivedAmountMismatch();
    error ReentrancyBlocked();

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event TreasuryUpdated(address indexed previousTreasury, address indexed newTreasury);
    event AcceptedTokenUpdated(address indexed token, bool accepted);

    /// @dev Keep this event shape compatible with the current backend verifier.
    event PaymentReceived(
        bytes32 indexed orderId,
        address indexed payer,
        uint256 amount,
        address token
    );

    struct PaymentRecord {
        address payer;
        address token;
        uint256 amount;
        uint64 paidAt;
    }

    address public owner;
    address public treasury;

    mapping(address => bool) public acceptedTokens;
    mapping(bytes32 => PaymentRecord) public payments;

    uint256 private _reentrancyLock;

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
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

    function setAcceptedToken(address token, bool accepted) external onlyOwner {
        if (token == address(0)) revert ZeroAddress();

        acceptedTokens[token] = accepted;
        emit AcceptedTokenUpdated(token, accepted);
    }

    /// @notice Pay with the chain native token. Forwards `msg.value` to `treasury`.
    /// @dev Current backend verification flow is built around ERC20 USDT payments.
    function payNative(bytes32 orderId) external payable nonReentrant {
        if (msg.value == 0) revert InvalidAmount();

        _recordPayment(orderId, msg.sender, address(0), msg.value);
        _safeTransferNative(treasury, msg.value);
    }

    /// @notice Pay with an accepted ERC20 token such as BSC USDT. Pulls from payer to `treasury`.
    /// @dev User must approve this contract; funds never sit in this contract.
    function payToken(bytes32 orderId, address token, uint256 amount) external nonReentrant {
        if (!acceptedTokens[token]) revert UnsupportedToken();
        if (amount == 0) revert InvalidAmount();

        _recordPayment(orderId, msg.sender, token, amount);
        _transferExactTokenToTreasury(token, msg.sender, amount);
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
            paidAt: uint64(block.timestamp)
        });

        emit PaymentReceived(orderId, payer, amount, token);
    }

    function _transferExactTokenToTreasury(address token, address from, uint256 amount) internal {
        uint256 balanceBefore = IERC20Minimal(token).balanceOf(treasury);
        _safeTransferFromToken(token, from, treasury, amount);
        uint256 balanceAfter = IERC20Minimal(token).balanceOf(treasury);

        if (balanceAfter - balanceBefore != amount) revert ReceivedAmountMismatch();
    }

    function _safeTransferNative(address to, uint256 amount) internal {
        (bool success, ) = payable(to).call{value: amount}("");
        if (!success) revert TransferFailed();
    }

    function _safeTransferFromToken(address token, address from, address to, uint256 amount) internal {
        (bool success, bytes memory data) =
            token.call(abi.encodeWithSelector(IERC20Minimal.transferFrom.selector, from, to, amount));

        if (!success || (data.length != 0 && !abi.decode(data, (bool)))) {
            revert TransferFailed();
        }
    }
}
