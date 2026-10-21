// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract Vault is ReentrancyGuard {
    error Vault__ZeroDeposit();
    error Vault__InsufficientBalance();
    error Vault__TransferFailed();

    mapping(address => uint256) public balances;

    event Deposited(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);

    function deposit() external payable {
        if (msg.value == 0) revert Vault__ZeroDeposit();
        balances[msg.sender] += msg.value;
        emit Deposited(msg.sender, msg.value);
    }

    function withdraw(uint256 amount) external nonReentrant {
        // Checks
        if (balances[msg.sender] < amount) revert Vault__InsufficientBalance();
        // Effects
        balances[msg.sender] -= amount;
        emit Withdrawn(msg.sender, amount);
        // Interactions
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        if (!ok) revert Vault__TransferFailed();
    }
}
