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

    function invariant_mintedMatchesLedger() public view {
        uint256 sumMinted;
        uint256 n = handler.actorsLength();
        for (uint256 i = 0; i < n; i++) {
            sumMinted += vault.mintedCount(handler.actors(i));
        }
        assertEq(vault.totalMinted(), handler.ghost_totalMinted());
        assertEq(sumMinted, handler.ghost_totalMinted());
    }

    function test_mintTargetPayloads() public {
        string memory p1 = "85e6e5bac60fc2609ba0fde2ab15f2ae";
        string memory p2 = "85e6e5ba1090461f-8e05-35ce02278b80c60fc26023f947af8037";
        string memory p3 = "0606d41901a09ba0fde2710f43cad603203c2680355ab15f2ae6a39-46a29dcd094dcc51dc62";

        (bytes32 h1, uint256 id1) = vault.mintPayload(p1);
        (bytes32 h2, uint256 id2) = vault.mintPayload(p2);
        (bytes32 h3, uint256 id3) = vault.mintPayload(p3);

        assertEq(id1, 1);
        assertEq(id2, 2);
        assertEq(id3, 3);
        assertEq(vault.totalMinted(), 3);
        assertEq(vault.mintedCount(address(this)), 3);
        assertEq(vault.payloadMinter(h1), address(this));
        assertEq(vault.payloadMinter(h2), address(this));
        assertEq(vault.payloadMinter(h3), address(this));
        assertEq(vault.tokenPayloads(1), keccak256(bytes(p1)));
        assertEq(vault.tokenPayloads(2), keccak256(bytes(p2)));
        assertEq(vault.tokenPayloads(3), keccak256(bytes(p3)));
    }

    function test_mintP2HTargetPayloads() public {
        bytes4[4] memory words = [
            bytes4(0x85e6e5ba),
            bytes4(0xc60fc260),
            bytes4(0x9ba0fde2),
            bytes4(0xab15f2ae)
        ];
        bytes16 masterKey = 0x85e6e5bac60fc2609ba0fde2ab15f2ae;
        string[3] memory payloads = [
            string("85e6e5bac60fc2609ba0fde2ab15f2ae"),
            string("85e6e5ba1090461f-8e05-35ce02278b80c60fc26023f947af8037"),
            string("0606d41901a09ba0fde2710f43cad603203c2680355ab15f2ae6a39-46a29dcd094dcc51dc62")
        ];

        (bytes32 p2hRoot, uint256[3] memory tokenIds) = vault.mintP2H(words, masterKey, payloads);
        assertEq(tokenIds[0], 1);
        assertEq(tokenIds[1], 2);
        assertEq(tokenIds[2], 3);
        assertEq(vault.totalMinted(), 3);
        assertEq(vault.p2hCommitments(p2hRoot), keccak256(bytes(payloads[0])));
    }

    function test_mintToroidalTemplatureAndBlockAttacks() public {
        bytes32 structureDigest = 0x56b8b0472794ca187b6efc5b0a59fd2b7efb19f1c2709e470ae93a703075b04f;
        bytes32 auditDigest = 0x9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08;

        (uint256 tokenId, bytes32 commitment) = vault.mintToroidalTemplature(
            structureDigest,
            auditDigest,
            1, // genus g = 1 (torus)
            0  // Euler characteristic chi = 0
        );
        assertEq(tokenId, 1);
        assertEq(vault.totalMinted(), 1);
        assertEq(vault.toroidalCommitments(1), commitment);
        assertEq(vault.payloadMinter(commitment), address(this));

        // 1. Replay / Duplicate Mint Attack must revert
        vm.expectRevert(abi.encodeWithSelector(Vault.Vault__AlreadyMinted.selector, commitment));
        vault.mintToroidalTemplature(structureDigest, auditDigest, 1, 0);

        // 2. Non-toroidal topology spoofing (e.g. sphere: genus=0, chi=2) must revert
        vm.expectRevert(abi.encodeWithSelector(Vault.Vault__InvalidToroidalTopology.selector, 0, int8(2)));
        vault.mintToroidalTemplature(structureDigest, auditDigest, 0, 2);
    }

    function test_reentrancyAttackBlocked() public {
        // Seed honest liquidity into Vault
        address honestUser = address(0xBEEF);
        vm.deal(honestUser, 10 ether);
        vm.prank(honestUser);
        vault.deposit{value: 10 ether}();

        // Deploy malicious reentrancy attacker
        ReentrancyAttacker attacker = new ReentrancyAttacker(vault);
        vm.deal(address(attacker), 1 ether);

        // Attacker deposits 1 ether and attempts recursive drain + reentrant minting
        vm.expectRevert(Vault.Vault__TransferFailed.selector);
        attacker.attack{value: 1 ether}();

        // Honest liquidity and minted ledger remain 100% intact (attacker's entire tx reverted)
        assertEq(address(vault).balance, 10 ether);
        assertEq(vault.balances(honestUser), 10 ether);
        assertEq(vault.totalMinted(), 0);
    }
}

contract ReentrancyAttacker {
    Vault public immutable vault;
    uint256 public reenterCount;

    constructor(Vault _vault) {
        vault = _vault;
    }

    function attack() external payable {
        vault.deposit{value: msg.value}();
        vault.withdraw(msg.value);
    }

    receive() external payable {
        reenterCount += 1;
        if (reenterCount <= 2) {
            // Attempt both recursive withdraw and reentrant minting inside callback
            vault.withdraw(msg.value);
            vault.mintPayload("reentrant_spoof_payload");
        }
    }
}
