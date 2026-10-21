// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {Test} from "forge-std/Test.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";
import {Vault} from "../src/Vault.sol";
import {VaultHandler} from "./handlers/VaultHandler.sol";

contract VaultInvariantTest is StdInvariant, Test {
    Vault internal vault;
    VaultHandler internal handler;

    function setUp() public {
        vault = new Vault();
        handler = new VaultHandler(vault);
        targetContract(address(handler));
    }

    function invariant_balanceMatchesLedger() public view {
        assertEq(address(vault).balance, handler.ghost_totalDeposited() - handler.ghost_totalWithdrawn());
    }

    function invariant_sumOfBalancesMatchesEth() public view {
        uint256 sum;
        uint256 n = handler.actorsLength();
        for (uint256 i = 0; i < n; i++) {
            sum += vault.balances(handler.actors(i));
        }
        assertEq(sum, address(vault).balance);
    }
}
