import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ReactFlow, useNodesState, useEdgesState, Controls, Background, MarkerType, Handle, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import './FlowGraph.css';

const nodeWidth = 250;
const nodeHeight = 80;

const getLayoutedElements = (nodes, edges, direction = 'TB') => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));

    dagreGraph.setGraph({
        rankdir: direction,
        nodesep: 80, // Horizontal space between nodes
        ranksep: 100  // Vertical space between ranks
    });

    nodes.forEach((node) => {
        dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
    });

    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });

    dagre.layout(dagreGraph);

    const layoutedNodes = nodes.map((node) => {
        const nodeWithPosition = dagreGraph.node(node.id);
        return {
            ...node,
            position: {
                x: nodeWithPosition.x - nodeWidth / 2,
                y: nodeWithPosition.y - nodeHeight / 2,
            },
        };
    });

    return { nodes: layoutedNodes, edges };
};

const truncate = (str, len = 60) => {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
};

const TurnNode = ({ data }) => {

    const isTurn = data.role === 'turn';
    const isSystem = data.role === 'system';

    // Style logic
    // If it's a turn, we split it. If it's system/other, we center it.
    // Selection now managed manually via data.isSelected

    return (
        <div style={{
            width: '100%',
            height: '100%',
            border: data.isSelected ? '2px solid #a855f7' : (data.isCurrent ? '2px solid #ef4444' : '1px solid #334155'),
            borderRadius: '8px',
            backgroundColor: '#1e293b',
            color: '#f1f5f9',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            fontSize: '12px',
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
        }}>
            <Handle type="target" position={Position.Top} style={{ background: '#555', w: 8, h: 8 }} />
            {isTurn ? (
                <>
                    <div style={{
                        padding: '6px 8px',
                        borderBottom: '1px solid #334155',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        color: '#60a5fa',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                    }}>
                        <strong>User:</strong> {truncate(data.userContent)}
                    </div>
                    <div style={{
                        padding: '6px 8px',
                        flex: 1,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: 'vertical'
                    }}>
                        <strong>AI:</strong> {truncate(data.assistantContent)}
                    </div>
                </>
            ) : (
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '100%',
                    padding: '8px',
                    textAlign: 'center',
                    backgroundColor: isSystem ? 'rgba(16, 185, 129, 0.1)' : 'transparent',
                    color: isSystem ? '#34d399' : '#f1f5f9'
                }}>
                    <strong>{isSystem ? 'System' : data.role}:</strong> {truncate(data.fullContent)}
                </div>
            )}
            <Handle type="source" position={Position.Bottom} style={{ background: '#555', w: 8, h: 8 }} />
        </div>
    );
};

const nodeTypes = {
    custom: TurnNode,
};

const FlowGraph = ({ data, onNodeClick, onSelectionChange, currentId }) => {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [selectedIds, setSelectedIds] = useState([]);

    // Transform raw data (flat nodes list) into ReactFlow elements
    useEffect(() => {
        if (!data || data.length === 0) return;

        // 1. Build a map for easy lookup
        const nodeMap = new Map();
        data.forEach(n => nodeMap.set(n.id, { ...n, children: [] }));

        // 2. Populate children
        data.forEach(n => {
            const pIds = n.parent_ids || (n.parent_id ? [n.parent_id] : []);
            pIds.forEach(pid => {
                if (nodeMap.has(pid)) {
                    nodeMap.get(pid).children.push(n.id);
                }
            });
        });

        // 2.5 COLLAPSE PASS: Remove <FORK> nodes and reconnect
        const nodesToProcess = Array.from(nodeMap.values());
        nodesToProcess.forEach(node => {
            if (node.role === 'system' && node.content && node.content.includes('<FORK>')) {
                // This is a fork node. We will remove it.
                // 1. Get Parents (P)
                const pIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);

                // 2. Get Children (C)
                const childrenIds = node.children;

                // 3. Rewire Children to point to Parents
                childrenIds.forEach(childId => {
                    const child = nodeMap.get(childId);
                    if (child) {
                        // Remove fork node from child's parent_ids
                        let childPIds = child.parent_ids || (child.parent_id ? [child.parent_id] : []);
                        childPIds = childPIds.filter(id => id !== node.id);

                        // Add fork's parents to child's parent_ids
                        // Avoid duplicates
                        pIds.forEach(pid => {
                            if (!childPIds.includes(pid)) childPIds.push(pid);
                        });

                        child.parent_ids = childPIds;
                    }
                });

                // 4. Rewire Parents to point to Children (update children arrays)
                pIds.forEach(pid => {
                    const parent = nodeMap.get(pid);
                    if (parent) {
                        // Remove fork node from parent's children
                        parent.children = parent.children.filter(id => id !== node.id);
                        // Add fork's children
                        childrenIds.forEach(cid => {
                            if (!parent.children.includes(cid)) parent.children.push(cid);
                        });
                    }
                });

                // 5. Remove Fork Node from map
                nodeMap.delete(node.id);
            }
        });

        const initialNodes = [];
        const initialEdges = [];
        const processedIds = new Set();
        const mergedMap = new Map(); // Old ID -> New ID

        // 3. Identification Pass: Find User->Assistant pairs
        Array.from(nodeMap.values()).forEach(node => {
            if (processedIds.has(node.id)) return;

            // Candidate for merge: User node with exactly 1 child, and that child is Assistant
            if (node.role === 'user' && node.children.length === 1) {
                const childId = node.children[0];
                const child = nodeMap.get(childId);

                // Check if child is assistant and hasn't been processed
                if (child && child.role === 'assistant' && !processedIds.has(child.id)) {
                    // MERGE!
                    // We use the CHILD's ID as the main ID for the merged node
                    // (because that represents the state after the turn is complete).
                    const mergedId = child.id;

                    initialNodes.push({
                        id: mergedId,
                        type: 'custom',
                        selectable: false,
                        data: {
                            role: 'turn',
                            userContent: node.content,
                            assistantContent: child.content,
                            isCurrent: mergedId === currentId || node.id === currentId,
                            fullContent: "Merged Turn"
                        },
                        position: { x: 0, y: 0 },
                        style: { width: nodeWidth, height: 100 } // Higher for merged
                    });

                    processedIds.add(node.id);
                    processedIds.add(child.id);
                    mergedMap.set(node.id, mergedId);
                    mergedMap.set(child.id, mergedId);
                    return;
                }
            }

            // Default: Single Node
            initialNodes.push({
                id: node.id,
                type: 'custom',
                selectable: false,
                data: {
                    role: node.role,
                    fullContent: node.content,
                    isCurrent: node.id === currentId
                },
                position: { x: 0, y: 0 },
                style: { width: nodeWidth, height: 60 }
            });
            processedIds.add(node.id);
            mergedMap.set(node.id, node.id);
        });

        // 4. Edges Pass
        // We iterate original nodes to reconstruct edges, but mapping IDs to merged ones.
        const edgeSet = new Set(); // dedupe

        Array.from(nodeMap.values()).forEach(node => {
            const targetId = mergedMap.get(node.id);
            if (!targetId) return; // Should not happen

            const pIds = node.parent_ids || (node.parent_id ? [node.parent_id] : []);

            pIds.forEach(srcRawId => {
                const sourceId = mergedMap.get(srcRawId);
                if (sourceId && sourceId !== mergedMap.get(node.id)) {
                    // Determine targetId again just to be safe in loop context, though we have it const above
                    // Correction: targetId is fixed for this node iteration.
                    // We check if sourceId !== targetId to avoid self-loops from internal merge

                    if (sourceId && sourceId !== targetId) {
                        const edgeKey = `${sourceId}-${targetId}`;
                        if (!edgeSet.has(edgeKey)) {
                            initialEdges.push({
                                id: edgeKey,
                                source: sourceId,
                                target: targetId,
                                type: 'default',
                                markerEnd: { type: MarkerType.ArrowClosed },
                                style: { stroke: '#334155', strokeWidth: 2 }
                            });
                            edgeSet.add(edgeKey);
                        }
                    }
                }
            });
        });

        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
            initialNodes,
            initialEdges
        );

        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
    }, [data, currentId, setNodes, setEdges]);


    // Manual selection handler for Cmd+click
    const handleNodeClick = useCallback((e, node) => {
        if (e.metaKey || e.ctrlKey) {
            // Toggle selection
            const newSelectedIds = selectedIds.includes(node.id)
                ? selectedIds.filter(id => id !== node.id)
                : [...selectedIds, node.id];

            setSelectedIds(newSelectedIds);
            onSelectionChange(newSelectedIds);

            // Update node visuals
            setNodes(nds => nds.map(n => ({
                ...n,
                data: { ...n.data, isSelected: newSelectedIds.includes(n.id) }
            })));
        }

        // Always navigate
        onNodeClick(e, node.id);
    }, [selectedIds, onNodeClick, onSelectionChange, setNodes]);

    return (
        <div style={{ width: '100%', height: '100%' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={handleNodeClick}
                fitView
                attributionPosition="bottom-left"
                minZoom={0.1}
                style={{ backgroundColor: '#020617' }}
            >
                <Controls />
                <Background color="#334155" gap={20} size={1} />
            </ReactFlow>
        </div>
    );
};

export default FlowGraph;
