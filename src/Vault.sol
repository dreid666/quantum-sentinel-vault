// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract Vault is ReentrancyGuard {
    error Vault__ZeroDeposit();
    error Vault__InsufficientBalance();
    error Vault__TransferFailed();
    error Vault__EmptyPayload();
    error Vault__AlreadyMinted(bytes32 payloadHash);
    error Vault__InvalidP2HProof();
    error Vault__InvalidToroidalTopology(uint8 genus, int8 eulerCharacteristic);

    mapping(address => uint256) public balances;
    mapping(bytes32 => address) public payloadMinter;
    mapping(uint256 => bytes32) public tokenPayloads;
    mapping(bytes32 => bytes32) public p2hCommitments;
    mapping(uint256 => bytes32) public toroidalCommitments;
    mapping(address => uint256) public mintedCount;
    uint256 public totalMinted;

    event Deposited(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);
    event PayloadMinted(
        address indexed minter,
        bytes32 indexed payloadHash,
        uint256 indexed tokenId,
        string payload
    );
    event P2HMinted(
        address indexed minter,
        bytes32 indexed p2hRoot,
        bytes16 masterKey,
        uint256[3] tokenIds
    );
    event ToroidalTemplatureMinted(
        address indexed minter,
        uint256 indexed tokenId,
        bytes32 indexed toroidalCommitment,
        bytes32 structureDigest,
        bytes32 auditDigest
    );

    function deposit() external payable {
        if (msg.value == 0) revert Vault__ZeroDeposit();
        balances[msg.sender] += msg.value;
        emit Deposited(msg.sender, msg.value);
    }

    function mintPayload(string calldata payload)
        public
        nonReentrant
        returns (bytes32 payloadHash, uint256 tokenId)
    {
        if (bytes(payload).length == 0) revert Vault__EmptyPayload();
        payloadHash = keccak256(bytes(payload));
        if (payloadMinter[payloadHash] != address(0)) {
            revert Vault__AlreadyMinted(payloadHash);
        }
        tokenId = ++totalMinted;
        payloadMinter[payloadHash] = msg.sender;
        tokenPayloads[tokenId] = payloadHash;
        mintedCount[msg.sender] += 1;
        emit PayloadMinted(msg.sender, payloadHash, tokenId, payload);
    }

    function mintP2H(
        bytes4[4] calldata words,
        bytes16 expectedMaster,
        string[3] calldata payloads
    ) external returns (bytes32 p2hRoot, uint256[3] memory tokenIds) {
        bytes16 reconstructed = bytes16(
            bytes.concat(words[0], words[1], words[2], words[3])
        );
        if (reconstructed != expectedMaster) revert Vault__InvalidP2HProof();

        bytes32 h1;
        bytes32 h2;
        bytes32 h3;
        (h1, tokenIds[0]) = mintPayload(payloads[0]);
        (h2, tokenIds[1]) = mintPayload(payloads[1]);
        (h3, tokenIds[2]) = mintPayload(payloads[2]);

        p2hRoot = keccak256(abi.encodePacked(reconstructed, h1, h2, h3));
        p2hCommitments[p2hRoot] = h1;
        emit P2HMinted(msg.sender, p2hRoot, reconstructed, tokenIds);
    }

    function mintHash(bytes32 payloadHash)
        external
        nonReentrant
        returns (uint256 tokenId)
    {
        if (payloadHash == bytes32(0)) revert Vault__EmptyPayload();
        if (payloadMinter[payloadHash] != address(0)) {
            revert Vault__AlreadyMinted(payloadHash);
        }
        tokenId = ++totalMinted;
        payloadMinter[payloadHash] = msg.sender;
        tokenPayloads[tokenId] = payloadHash;
        mintedCount[msg.sender] += 1;
        emit PayloadMinted(msg.sender, payloadHash, tokenId, "");
    }

    function mintToroidalTemplature(
        bytes32 structureDigest,
        bytes32 auditDigest,
        uint8 genus,
        int8 eulerCharacteristic
    ) external nonReentrant returns (uint256 tokenId, bytes32 toroidalCommitment) {
        if (genus != 1 || eulerCharacteristic != 0) {
            revert Vault__InvalidToroidalTopology(genus, eulerCharacteristic);
        }
        if (structureDigest == bytes32(0) || auditDigest == bytes32(0)) {
            revert Vault__EmptyPayload();
        }
        toroidalCommitment = keccak256(
            abi.encodePacked(
                "TOROIDAL_TEMPLATURE_T2",
                structureDigest,
                auditDigest,
                genus,
                eulerCharacteristic
            )
        );
        if (payloadMinter[toroidalCommitment] != address(0)) {
            revert Vault__AlreadyMinted(toroidalCommitment);
        }
        tokenId = ++totalMinted;
        payloadMinter[toroidalCommitment] = msg.sender;
        tokenPayloads[tokenId] = toroidalCommitment;
        toroidalCommitments[tokenId] = toroidalCommitment;
        mintedCount[msg.sender] += 1;
        emit ToroidalTemplatureMinted(
            msg.sender,
            tokenId,
            toroidalCommitment,
            structureDigest,
            auditDigest
        );
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
