// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {CommonBase} from "forge-std/Base.sol";
import {StdCheats} from "forge-std/StdCheats.sol";
import {StdUtils} from "forge-std/StdUtils.sol";
import {Vault} from "../../src/Vault.sol";

contract VaultHandler is CommonBase, StdCheats, StdUtils {
    Vault public immutable vault;
    address[] public actors;

    uint256 public ghost_totalDeposited;
    uint256 public ghost_totalWithdrawn;
    mapping(address => uint256) public ghost_userBalances;

    constructor(Vault _vault) {
        vault = _vault;
        for (uint256 i = 0; i < 5; i++) {
            address actor = address(uint160(0xA000 + i));
            actors.push(actor);
            vm.deal(actor, 1_000 ether);
        }
    }

    function actorsLength() external view returns (uint256) {
        return actors.length;
    }

    function deposit(uint256 actorSeed, uint256 amount) external {
        address actor = actors[actorSeed % actors.length];
        amount = bound(amount, 1, 100 ether);
        if (actor.balance < amount) return;

        vm.prank(actor);
        vault.deposit{value: amount}();

        ghost_totalDeposited += amount;
        ghost_userBalances[actor] += amount;
    }

    function withdraw(uint256 actorSeed, uint256 amount) external {
        address actor = actors[actorSeed % actors.length];
        uint256 bal = ghost_userBalances[actor];
        if (bal == 0) return;
        amount = bound(amount, 1, bal);

        vm.prank(actor);
        vault.withdraw(amount);

        ghost_totalWithdrawn += amount;
        ghost_userBalances[actor] -= amount;
    }
}
