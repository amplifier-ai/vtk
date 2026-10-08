// VTK: suppress -Wreserved-identifier warnings until ragel is fixed:
// <https://github.com/adrian-thurston/ragel/issues/81>
#if defined(__clang__)
  #if defined(__has_warning)
    #if __has_warning("-Wreserved-identifier")
      #pragma clang diagnostic ignored "-Wreserved-identifier"
    #endif
  #endif
#endif

#include "vtkStringScanner.h"

// This is a ragel file for generating a parser for MTL files
// Note that some MTL files are whitespace sensitive
// Mainly with unquoted string names with spaces
// ala
//
// newmtl material name with spaces and no quotes
//
// or
//
// map_Kd my texture file.png
//




static const char _simple_lexer_actions[] = {
  0, 1, 0, 1, 1, 1, 3, 1,
  4, 1, 8, 1, 9, 1, 10, 1,
  11, 1, 12, 1, 13, 1, 14, 1,
  15, 2, 2, 0, 2, 5, 0, 4,
  5, 2, 0, 7, 4, 5, 2, 6,
  0
};

static const char _simple_lexer_key_offsets[] = {
  0, 2, 3, 13, 16, 20, 21, 26,
  31, 37
};

static const char _simple_lexer_trans_keys[] = {
  10, 13, 10, 10, 13, 32, 35, 43,
  45, 9, 12, 48, 57, 32, 9, 13,
  9, 32, 11, 12, 10, 10, 13, 32,
  9, 12, 32, 9, 13, 48, 57, 32,
  46, 9, 13, 48, 57, 32, 9, 13,
  48, 57, 0
};

static const char _simple_lexer_single_lengths[] = {
  2, 1, 6, 1, 2, 1, 3, 1,
  2, 1
};

static const char _simple_lexer_range_lengths[] = {
  0, 0, 2, 1, 1, 0, 1, 2,
  2, 2
};

static const char _simple_lexer_index_offsets[] = {
  0, 3, 5, 14, 17, 21, 23, 28,
  32, 37
};

static const char _simple_lexer_indicies[] = {
  2, 3, 1, 2, 0, 6, 7, 5,
  8, 9, 9, 5, 10, 4, 11, 11,
  4, 5, 5, 5, 12, 6, 13, 2,
  3, 1, 1, 8, 11, 11, 10, 4,
  14, 15, 14, 10, 4, 16, 16, 17,
  4, 0
};

static const char _simple_lexer_trans_targs[] = {
  2, 0, 2, 1, 3, 4, 2, 5,
  6, 7, 8, 2, 2, 2, 2, 9,
  2, 9
};

static const char _simple_lexer_trans_actions[] = {
  21, 0, 9, 0, 1, 3, 11, 0,
  28, 25, 25, 15, 17, 19, 13, 31,
  23, 36
};

static const char _simple_lexer_to_state_actions[] = {
  0, 0, 5, 0, 0, 0, 0, 0,
  0, 0
};

static const char _simple_lexer_from_state_actions[] = {
  0, 0, 7, 0, 0, 0, 0, 0,
  0, 0
};

static const char _simple_lexer_eof_trans[] = {
  1, 1, 0, 12, 13, 14, 12, 12,
  15, 17
};

static const int simple_lexer_start = 2;
static const int simple_lexer_first_final = 2;
static const int simple_lexer_error = -1;

static const int simple_lexer_en_main = 2;



int parseMTL(
  const char *start,
  std::vector<Token>  &tokens
)
{
  int act, cs, res = 0;
  const char *p = start;
  const char *pe = p + strlen(start) + 1;
  const char *eof = pe;
  const char *ts = nullptr;
  const char *te = nullptr;

  std::string recentString;
  std::string recentSpace;
  std::string currentNum;


  {
  cs = simple_lexer_start;
  ts = nullptr;
  te = nullptr;
  act = 0;
  }


  {
  int _klen;
  unsigned int _trans;
  const char *_acts;
  unsigned int _nacts;
  const char *_keys;

  if ( p == pe )
    goto _test_eof;
_resume:
  _acts = _simple_lexer_actions + _simple_lexer_from_state_actions[cs];
  _nacts = (unsigned int) *_acts++;
  while ( _nacts-- > 0 ) {
    switch ( *_acts++ ) {
  case 4:
  {ts = p;}
  break;
    }
  }

  _keys = _simple_lexer_trans_keys + _simple_lexer_key_offsets[cs];
  _trans = _simple_lexer_index_offsets[cs];

  _klen = _simple_lexer_single_lengths[cs];
  if ( _klen > 0 ) {
    const char *_lower = _keys;
    const char *_mid;
    const char *_upper = _keys + _klen - 1;
    while (true) {
      if ( _upper < _lower )
        break;

      _mid = _lower + ((_upper-_lower) >> 1);
      if ( (*p) < *_mid )
        _upper = _mid - 1;
      else if ( (*p) > *_mid )
        _lower = _mid + 1;
      else {
        _trans += (unsigned int)(_mid - _keys);
        goto _match;
      }
    }
    _keys += _klen;
    _trans += _klen;
  }

  _klen = _simple_lexer_range_lengths[cs];
  if ( _klen > 0 ) {
    const char *_lower = _keys;
    const char *_mid;
    const char *_upper = _keys + (_klen<<1) - 2;
    while (true) {
      if ( _upper < _lower )
        break;

      _mid = _lower + (((_upper-_lower) >> 1) & ~1);
      if ( (*p) < _mid[0] )
        _upper = _mid - 2;
      else if ( (*p) > _mid[1] )
        _lower = _mid + 2;
      else {
        _trans += (unsigned int)((_mid - _keys)>>1);
        goto _match;
      }
    }
    _trans += _klen;
  }

_match:
  _trans = _simple_lexer_indicies[_trans];
_eof_trans:
  cs = _simple_lexer_trans_targs[_trans];

  if ( _simple_lexer_trans_actions[_trans] == 0 )
    goto _again;

  _acts = _simple_lexer_actions + _simple_lexer_trans_actions[_trans];
  _nacts = (unsigned int) *_acts++;
  while ( _nacts-- > 0 )
  {
    switch ( *_acts++ )
    {
  case 0:
  { recentString += *p;  }
  break;
  case 1:
  { recentSpace += *p;  }
  break;
  case 2:
  { currentNum += *p;  }
  break;
  case 5:
  {te = p+1;}
  break;
  case 6:
  {act = 2;}
  break;
  case 7:
  {act = 3;}
  break;
  case 8:
  {te = p+1;{ currentNum.clear(); recentString.clear(); recentSpace.clear(); }}
  break;
  case 9:
  {te = p+1;{
      Token tok;
      tok.Type = Token::LineEnd;
      tokens.push_back(tok);
      currentNum.clear(); recentString.clear(); recentSpace.clear();
    }}
  break;
  case 10:
  {te = p;p--;{
    currentNum += '\0';
    Token tok;
    tok.StringValue = currentNum;
    VTK_FROM_CHARS_IF_ERROR_BREAK(currentNum, tok.NumberValue);
    tok.Type = Token::Number;
    tokens.push_back(tok);
    currentNum.clear();
    recentString.clear();
    recentSpace.clear();
  }}
  break;
  case 11:
  {te = p;p--;{
    Token tok;
    tok.StringValue = recentString;
    tok.Type = Token::String;
    tokens.push_back(tok);
    recentString.clear();
    currentNum.clear();
    recentSpace.clear();
  }}
  break;
  case 12:
  {te = p;p--;{
    Token tok;
    tok.StringValue = recentSpace;
    tok.Type = Token::Space;
    tokens.push_back(tok);
    recentSpace.clear();
    currentNum.clear();
    recentString.clear();
  }}
  break;
  case 13:
  {te = p;p--;{ std::string value = "Error unknown text: "; value += std::string(ts, te-ts); std::cerr << value << "\n"; }}
  break;
  case 14:
  {{p = ((te))-1;}{
    Token tok;
    tok.StringValue = recentString;
    tok.Type = Token::String;
    tokens.push_back(tok);
    recentString.clear();
    currentNum.clear();
    recentSpace.clear();
  }}
  break;
  case 15:
  {  switch( act ) {
  case 2:
  {{p = ((te))-1;}
    currentNum += '\0';
    Token tok;
    tok.StringValue = currentNum;
    VTK_FROM_CHARS_IF_ERROR_BREAK(currentNum, tok.NumberValue);
    tok.Type = Token::Number;
    tokens.push_back(tok);
    currentNum.clear();
    recentString.clear();
    recentSpace.clear();
  }
  break;
  case 3:
  {{p = ((te))-1;}
    Token tok;
    tok.StringValue = recentString;
    tok.Type = Token::String;
    tokens.push_back(tok);
    recentString.clear();
    currentNum.clear();
    recentSpace.clear();
  }
  break;
  }
  }
  break;
    }
  }

_again:
  _acts = _simple_lexer_actions + _simple_lexer_to_state_actions[cs];
  _nacts = (unsigned int) *_acts++;
  while ( _nacts-- > 0 ) {
    switch ( *_acts++ ) {
  case 3:
  {ts = nullptr;}
  break;
    }
  }

  if ( ++p != pe )
    goto _resume;
  _test_eof: {}
  if ( p == eof )
  {
  if ( _simple_lexer_eof_trans[cs] > 0 ) {
    _trans = _simple_lexer_eof_trans[cs] - 1;
    goto _eof_trans;
  }
  }

  }


  return res;
}
