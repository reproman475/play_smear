import React, { Component } from 'react';
import { withRouter } from 'react-router-dom';
import { Spin, Input, Popover, Button, Row, Col } from 'antd';
import {
  UserOutlined,
  TeamOutlined,
  TrophyOutlined,
  LockOutlined
} from '@ant-design/icons';
import './GameList.css';

class GameList extends Component {
  state = {
  }

  onChangeInput = (e) => {
    this.setState({[e.target.name]: e.target.value});
  }

  render() {
    const { signedInUser, initLoading, gameList, handleDelete, handleJoin, handleResume, handleSpectate } = this.props;

    const title = this.props.mode === 'public' ? "Join a game started by someone else" : "Manage My Games";
    
    const games = gameList.map(game =>
      <div className="GameList" key={game.id}>
        <Row type="flex" align="middle">
          <Col className="GameName" xs={12} md={6}>
            {this.props.mode === 'manage' ? (
              <b style={{cursor: "pointer"}} onClick={() => handleResume(game.id)}>{game.name}</b>
            ) : (
              <b>{game.name}</b>
            )}
          </Col>
          <Col className="GameIcons" xs={12} md={6}>
            <Popover placement="topLeft" content="The number of players who have joined out of the total number of players this game accepts" title="Players">
              {game.players.length - game.num_spectators}/{game.num_players} <UserOutlined />
            </Popover>
            <span style={{padding: "5px"}}> </span>
            <Popover placement="topLeft" content="The number of teams in this game" title="Teams">
              {game.num_teams} <TeamOutlined />
            </Popover>
            <span style={{padding: "5px"}}> </span>
            <Popover placement="topLeft" content="The number of points needed to win this game" title="Points">
              {game.score_to_play_to} <TrophyOutlined />
            </Popover>
            <span style={{padding: "5px"}}> </span>
            { game.passcode_required &&
            <Popover placement="topLeft" content="A passcode is required to join this game" title="Passcode Required">
              <LockOutlined />
            </Popover>
            }
          </Col>
          <Col xs={24} md={12} align="right">
              {
                !game.loading && this.props.mode === 'manage' ?
                  (
                    <>
                      <Button disabled={game.state === "game_over"} style={{marginRight: "5px"}} onClick={() => handleResume(game.id)}>{game.state === "game_over" ? "Finished" : "Resume"}</Button>
                      <Button disabled={game.owner !== signedInUser.id} onClick={() => handleDelete(game.id)}>Delete Game</Button>
                    </>
                  ) :
                  (
                    <>
                      { game.passcode_required && (
                        <Input
                          className="passcodeInput"
                          placeholder="Passcode required"
                          name={`passcode_${game.id}`}
                          value={this.state[`passcode_${game.id}`]}
                          onChange={this.onChangeInput}
                          onPressEnter={() => handleJoin(game.id, this.state[`passcode_${game.id}`])}
                        />
                      )}
                      <Button onClick={() => handleJoin(game.id, this.state[`passcode_${game.id}`])}>Join</Button>
                      <Button onClick={() => handleSpectate(game.id, this.state[`passcode_${game.id}`])}>Spectate</Button>
                    </>
                  )
              }
          </Col>
        </Row>
      </div>
    );

    return (
      <>
        <div align="center">
          { initLoading && <Spin size="large" />}
        </div>
        <h2>{title}</h2>
        {games}
      </>
    );
  }
}

export default withRouter(GameList);
