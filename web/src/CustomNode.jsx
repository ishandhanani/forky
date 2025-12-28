import React from 'react';

const CustomNode = ({ nodeDatum, toggleNode, onNodeClick }) => {
    const { role, content, userContent, assistantContent } = nodeDatum;
    const isTurn = role === 'turn';
    const width = 250;
    const height = isTurn ? 100 : 60;
    const isCurrent = nodeDatum.attributes?.isCurrent;

    // Truncate helper
    const truncate = (str, len = 60) => {
        if (!str) return '';
        return str.length > len ? str.substring(0, len) + '...' : str;
    };

    const handleNodeClick = (e) => {
        if (e && e.stopPropagation) e.stopPropagation();
        onNodeClick(nodeDatum);
    };

    return (
        <g onClick={handleNodeClick} style={{ cursor: 'pointer' }}>
            <foreignObject x={-width / 2} y={-height / 2} width={width} height={height}>
                <div style={{
                    width: '100%',
                    height: '100%',
                    border: isCurrent ? '2px solid #ef4444' : '1px solid #334155',
                    borderRadius: '8px',
                    backgroundColor: '#1e293b',
                    color: '#f1f5f9',
                    display: 'flex',
                    flexDirection: 'column',
                    overflow: 'hidden',
                    fontSize: '12px',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                }}>
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
                                <strong>User:</strong> {truncate(userContent)}
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
                                <strong>AI:</strong> {truncate(assistantContent)}
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
                            backgroundColor: role === 'system' ? 'rgba(16, 185, 129, 0.1)' : 'transparent',
                            color: role === 'system' ? '#34d399' : '#f1f5f9'
                        }}>
                            <strong>{role === 'system' ? 'System' : role}:</strong> {truncate(content)}
                        </div>
                    )}
                </div>
            </foreignObject>
        </g>
    );
};

export default CustomNode;
